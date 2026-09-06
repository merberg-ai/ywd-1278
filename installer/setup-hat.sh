#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-/opt/ywd-1278/source}"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root

VENV=/opt/ywd-1278/venv
PROFILE="$SOURCE_ROOT/firmware/product-ax25r4.json"
DETECT="$SOURCE_ROOT/installer/hardware-detect.sh"
DEPLOY="$SOURCE_ROOT/installer/deploy-product-firmware.sh"
DEVICE="${YWD1278_MODEM_DEVICE:-/dev/ttyAMA0}"
PRODUCT_DIR=/var/lib/ywd-1278/product-firmware
PRODUCT_FIRMWARE="$PRODUCT_DIR/qualified-ax25r4.bin"
HARDWARE_RECORD=/var/lib/ywd-1278/firmware-hardware-qualified.json
BUILD_ROOT=""
BUILD_USER="${YWD1278_BUILD_USER:-${SUDO_USER:-}}"

cleanup(){ [[ -z "$BUILD_ROOT" || ! -d "$BUILD_ROOT" ]] || rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

[[ -n "$YWD_LOG_FILE" ]] || init_log /var/log/ywd-1278/install.log
for path in "$VENV/bin/python" "$PROFILE" "$DETECT" "$DEPLOY"; do
  [[ -e "$path" ]] || die "Required HAT setup path missing: $path"
done
[[ -e "$DEVICE" ]] || die "Radio UART not found: $DEVICE"
command_exists runuser || die "runuser is required for the unprivileged firmware build"

if [[ -z "$BUILD_USER" || "$BUILD_USER" == root || "$BUILD_USER" == "0" ]]; then
  candidate="$(logname 2>/dev/null || true)"
  [[ "$candidate" != root ]] && BUILD_USER="$candidate"
fi
[[ -n "$BUILD_USER" && "$BUILD_USER" != root ]] || die "Could not identify the non-root operator account for the firmware build"
id "$BUILD_USER" >/dev/null 2>&1 || die "Firmware build user does not exist: $BUILD_USER"

profile_get(){
  "$VENV/bin/python" - "$PROFILE" "$1" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p[sys.argv[2]])
PY
}

target="$(profile_get target_id)"
expected_identity="$(profile_get expected_identity)"
artifact_rel="$(profile_get artifact_relative_path)"
authorization_token="$(profile_get flash_authorization_token)"

section "Radio HAT setup"
step "Detecting attached MMDVM HAT"
if detect_out="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$DETECT" --device "$DEVICE" 2>&1)"; then
  detect_rc=0
else
  detect_rc=$?
fi
log_block "Guided HAT detection" "$detect_out"
[[ $detect_rc -eq 0 ]] || die "A supported MMDVM HAT could not be identified (rc=$detect_rc)"
detected_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect_out" | tail -1)"
identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$detect_out" | tail -1)"
firmware_class="$(sed -n 's/^FIRMWARE_CLASS=//p' <<<"$detect_out" | tail -1)"
[[ "$detected_target" == "$target" ]] || die "Detected HAT is not the supported AX25R4 product target"
ok "Supported MMDVM HAT detected"
step "$detected_target"
info "Current firmware: ${firmware_class:-UNKNOWN}"

case "$firmware_class" in
  STOCK)
    ok "Recognized factory firmware is installed"
    ;;
  YWD1278)
    [[ "$identity" == "$expected_identity" ]] || die "YWD-1278 firmware identity does not match the qualified AX25R4 image"
    ok "Qualified YWD-1278 firmware is already installed; programmed bytes will be reverified"
    ;;
  *)
    die "Guided setup supports exact recognized stock firmware or exact qualified YWD-1278 firmware only; current state is ${firmware_class:-UNKNOWN}"
    ;;
esac

section "Prepare qualified packet firmware"
BUILD_ROOT="$(mktemp -d /var/tmp/ywd1278-firmware-build.XXXXXX)"
tar -C "$SOURCE_ROOT" --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$BUILD_ROOT" -xf -
chown -R "$BUILD_USER":"$(id -gn "$BUILD_USER")" "$BUILD_ROOT"
run_logged "Building and verifying AX25R4 firmware" \
  runuser -u "$BUILD_USER" -- env YWD1278_FIRMWARE_BUILD_JOBS="${YWD1278_FIRMWARE_BUILD_JOBS:-}" \
  bash "$BUILD_ROOT/firmware/prepare-product-ax25r4.sh" || die "Qualified AX25R4 preparation failed"
built_artifact="$BUILD_ROOT/$artifact_rel"
[[ -f "$built_artifact" ]] || die "Firmware build completed without the expected artifact"
artifact_check="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" artifact --firmware "$built_artifact" 2>&1)" || die "Built firmware did not pass the product trust check"
log_block "Qualified firmware artifact trust" "$artifact_check"
install -d -m 0750 "$PRODUCT_DIR"
install -m 0640 "$built_artifact" "$PRODUCT_FIRMWARE"
persisted_check="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" artifact --firmware "$PRODUCT_FIRMWARE" 2>&1)" || die "Persisted firmware artifact did not pass re-verification"
log_block "Persisted firmware artifact trust" "$persisted_check"
ok "Exact qualified AX25R4 firmware is ready"
hint "Verified artifact stored at $PRODUCT_FIRMWARE"

preconfirmed=()
if [[ "$firmware_class" == STOCK ]]; then
  section "Install packet firmware"
  info "Before any write, YWD-1278 will make and verify a two-pass backup of the original HAT firmware."
  info "After programming, it independently reads the firmware back and verifies the exact YWD-1278 identity."
  if ! confirm_yes_no "Install YWD-1278 packet firmware on this HAT now?" yes; then
    die "Radio HAT firmware installation cancelled"
  fi
  preconfirmed=(--preconfirmed-write)
else
  section "Verify packet firmware"
  info "The HAT already reports the exact YWD-1278 identity; no rewrite is requested."
fi

step "Backing up, programming (if needed), and verifying the radio HAT"
if ! YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$DEPLOY" \
    --hardware-only --device "$DEVICE" \
    --firmware "$PRODUCT_FIRMWARE" \
    --authorize "$authorization_token" \
    "${preconfirmed[@]}" >>"$YWD_LOG_FILE" 2>&1; then
  fail "Radio HAT setup failed"
  info "Details: $YWD_LOG_FILE"
  exit 1
fi

check="$($VENV/bin/python -m ywd1278.install.hardware_trust --profile "$PROFILE" check-hardware \
  --firmware "$PRODUCT_FIRMWARE" --record "$HARDWARE_RECORD" 2>&1)" || die "Radio HAT qualification record did not verify"
log_block "Hardware qualification recheck" "$check"

post="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$DETECT" --device "$DEVICE" 2>&1)" || die "Radio HAT did not answer after firmware setup"
log_block "Post-setup HAT detection" "$post"
post_identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$post" | tail -1)"
[[ "$post_identity" == "$expected_identity" ]] || die "Radio HAT is not running the exact qualified YWD-1278 firmware after setup"

ok "Radio HAT is ready"
step "Original firmware rollback backup is verified and preserved"
step "AX25R4 programmed bytes and runtime identity are verified"
record_marker "YWD1278_GUIDED_HAT_SETUP=PASS"
record_marker "YWD1278_HAT_READY=YES"
record_marker "SERVICE_ELIGIBLE=NO"
record_marker "SERVICE_ENABLED=NO"
record_marker "RF_TRANSMITTED=NO"
