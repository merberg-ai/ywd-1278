#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root
banner

CONFIG=/etc/ywd-1278/config.toml
VENV=/opt/ywd-1278/venv
PROFILE="$SOURCE_ROOT/firmware/product-ax25r4.json"
TARGETS="$SOURCE_ROOT/firmware/targets.json"
HAT_CONTROL="$SOURCE_ROOT/firmware/hat_control.py"
HARDWARE_DETECT="$SOURCE_ROOT/installer/hardware-detect.sh"
LEGACY_FLASH="$SOURCE_ROOT/firmware/flash.sh"
FIRMWARE=""
STOCK_BACKUP_DIR=""
AUTHORIZE=""
READBACK_TMP=""
BOOTLOADER_ACTIVE=0
FLASH_WRITTEN=NO

cleanup(){
  if [[ $BOOTLOADER_ACTIVE -eq 1 && -n "${target:-}" ]]; then
    python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$target" >/dev/null 2>&1 || true
    BOOTLOADER_ACTIVE=0
  fi
  [[ -z "$READBACK_TMP" ]] || rm -f "$READBACK_TMP"
}
trap cleanup EXIT

usage(){
  cat <<'EOF'
Usage:
  sudo ./installer/deploy-product-firmware.sh --firmware FILE \
    --authorize FLASH-QUALIFIED-AX25R4 [--stock-backup-dir DIR] [--config FILE]

This is the explicit Stage-F product firmware gate. It never enables or starts
ywd-1278.service and it never enables RF TX. If the exact qualified AX25R4
firmware is already installed, the tool performs a programmed readback and
identity verification without rewriting flash.
EOF
}

while (($#)); do
  case "$1" in
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    --stock-backup-dir) STOCK_BACKUP_DIR="${2:?missing --stock-backup-dir value}"; shift ;;
    --authorize) AUTHORIZE="${2:?missing --authorize value}"; shift ;;
    --config) CONFIG="${2:?missing --config value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -x "$VENV/bin/python" ]] || die "Installed YWD-1278 venv not found: $VENV"
for path in "$PROFILE" "$TARGETS" "$HAT_CONTROL" "$HARDWARE_DETECT" "$LEGACY_FLASH" "$CONFIG"; do
  [[ -f "$path" ]] || die "Required Stage-F file missing: $path"
done
[[ -n "$FIRMWARE" && -f "$FIRMWARE" ]] || die "--firmware must name the exact prepared AX25R4 artifact"
command_exists stm32flash || die "stm32flash is required"
command_exists fuser || die "fuser is required"

profile_get(){
  local key="$1"
  "$VENV/bin/python" - "$PROFILE" "$key" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
v=obj.get(sys.argv[2])
if isinstance(v,bool): print('true' if v else 'false')
elif v is None: print('')
else: print(v)
PY
}

target="$(profile_get target_id)"
expected_identity="$(profile_get expected_identity)"
expected_sha="$(profile_get artifact_sha256)"
readback_bytes="$(profile_get programmed_readback_bytes)"
readback_sha="$(profile_get programmed_readback_sha256)"
flash_base="$(profile_get flash_base)"
expected_boot="$(profile_get expected_bootloader_version)"
expected_device_id="$(profile_get expected_device_id)"
authorization_token="$(profile_get flash_authorization_token)"
eligibility_record="$(profile_get service_eligibility_record)"

[[ "$AUTHORIZE" == "$authorization_token" ]] || die "Product firmware operation requires --authorize $authorization_token"

section "Stage-F runtime readiness"
set +e
readiness="$($VENV/bin/python -m ywd1278.install.readiness --config "$CONFIG" 2>&1)"
readiness_rc=$?
set -e
printf '%s\n' "$readiness"
[[ $readiness_rc -eq 0 ]] || die "Product runtime configuration must be READY before firmware deployment"
grep -q '^YWD1278_INSTALL_RUNTIME_READINESS=READY$' <<<"$readiness" || die "Runtime readiness marker missing"

mapfile -t configured < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print(d.get('hardware',{}).get('target',''))
print(d.get('radio',{}).get('device',''))
print('true' if d.get('radio',{}).get('tx_enabled',False) is True else 'false')
print('true' if d.get('firmware',{}).get('allow_automatic_flash',False) is True else 'false')
PY
)
configured_target="${configured[0]:-}"
device="${configured[1]:-}"
tx_enabled="${configured[2]:-true}"
auto_flash="${configured[3]:-true}"
[[ "$configured_target" == "$target" ]] || die "Configured HAT target does not exactly match product profile"
[[ -n "$device" && -e "$device" ]] || die "Configured modem UART does not exist: $device"
[[ "$tx_enabled" == false ]] || die "RF TX must remain disabled during Stage-F firmware deployment"
[[ "$auto_flash" == false ]] || die "Automatic firmware flashing must remain disabled"

section "Exact product artifact gate"
artifact_check="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" artifact --firmware "$FIRMWARE")" || die "Product artifact trust check failed"
printf '%s\n' "$artifact_check" | grep -v '^FLASH_WRITTEN=' || true
grep -q '^YWD1278_PRODUCT_FIRMWARE_ARTIFACT=PASS$' <<<"$artifact_check" || die "Artifact trust marker missing"
actual_sha="$(sha256sum "$FIRMWARE" | awk '{print $1}')"
[[ "$actual_sha" == "$expected_sha" ]] || die "Artifact digest changed after trust check"

section "Service/UART precondition"
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
if fuser "$device" >/dev/null 2>&1; then
  fail "UART is busy; Stage F refuses to stop an unknown owner automatically: $device"
  fuser -v "$device" >&2 || true
  exit 4
fi

section "Exact HAT identity gate"
set +e
detect="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$HARDWARE_DETECT" --device "$device" --config "$CONFIG" 2>&1)"
detect_rc=$?
set -e
printf '%s\n' "$detect"
[[ $detect_rc -eq 0 ]] || die "Supported HAT identity could not be established (rc=$detect_rc)"
detected_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect" | tail -1)"
identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$detect" | tail -1)"
[[ "$detected_target" == "$target" ]] || die "Detected HAT target mismatch"
[[ -n "$identity" ]] || die "Detected HAT identity is empty"

identity_is_stock(){
  "$VENV/bin/python" - "$TARGETS" "$target" "$identity" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
items=[x for x in obj.get('targets',[]) if x.get('id')==sys.argv[2]]
if len(items)!=1: raise SystemExit(2)
raise SystemExit(0 if sys.argv[3] in (items[0].get('stock_identities') or []) else 1)
PY
}

find_verified_stock_backup(){
  local base="/var/lib/ywd-1278/firmware-backups/$target" candidate
  [[ -d "$base" ]] || return 1
  while IFS= read -r candidate; do
    if "$VENV/bin/python" -m ywd1278.install.firmware_trust --profile "$PROFILE" backup --backup-dir "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(find "$base" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | cut -d' ' -f2-)
  return 1
}

section "Protected stock rollback gate"
if identity_is_stock; then
  info "Current application is exact allowlisted stock; taking a fresh protected two-pass stock backup before any write."
  backup_out="$(bash "$LEGACY_FLASH" backup --target "$target" --device "$device")" || die "Protected stock backup failed"
  printf '%s\n' "$backup_out"
  STOCK_BACKUP_DIR="$(sed -n 's/^BACKUP_DIR=//p' <<<"$backup_out" | tail -1)"
  [[ -n "$STOCK_BACKUP_DIR" ]] || die "Backup completed without BACKUP_DIR marker"
elif [[ -z "$STOCK_BACKUP_DIR" ]]; then
  STOCK_BACKUP_DIR="$(find_verified_stock_backup || true)"
  [[ -n "$STOCK_BACKUP_DIR" ]] || die "Current firmware is not stock and no verified stock rollback backup was supplied/found"
  info "Using previously verified stock rollback backup: $STOCK_BACKUP_DIR"
fi
backup_check="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" backup --backup-dir "$STOCK_BACKUP_DIR")" || die "Stock rollback backup failed product trust validation"
printf '%s\n' "$backup_check" | grep -v '^FLASH_WRITTEN=' || true
grep -q '^YWD1278_STOCK_BACKUP_TRUST=PASS$' <<<"$backup_check" || die "Stock backup trust marker missing"

# flash.sh restores any owners it stopped for backup. Product deployment never
# steals a UART after that restoration; it fails closed instead.
if fuser "$device" >/dev/null 2>&1; then
  fail "UART became busy after backup verification; refusing product flash"
  fuser -v "$device" >&2 || true
  exit 4
fi

validate_bootloader_info(){
  STM32FLASH_INFO="$1" "$VENV/bin/python" - "$expected_boot" "$expected_device_id" <<'PY'
import os,re,sys
text=os.environ.get('STM32FLASH_INFO','')
expected_version,expected_device=sys.argv[1:]
def grab(label):
    m=re.search(rf"{label}\s*:\s*(0x[0-9A-Fa-f]+)",text)
    return m.group(1).lower() if m else ''
version=grab('Version'); device=grab('Device ID')
if version != expected_version.lower() or device != expected_device.lower():
    print(f'BOOTLOADER_IDENTITY_MISMATCH version={version} device={device}',file=sys.stderr)
    raise SystemExit(1)
print(f'STM32_BOOTLOADER_VERSION={version}')
print(f'STM32_DEVICE_ID={device}')
print('STM32_BOOTLOADER_IDENTITY=PASS')
PY
}

enter_bootloader(){
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$target"
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  local info
  info="$(stm32flash -b 115200 "$device" 2>&1)" || { printf '%s\n' "$info" >&2; die "STM32 bootloader did not answer"; }
  printf '%s\n' "$info"
  validate_bootloader_info "$info" || die "STM32 bootloader identity mismatch"
}

restart_application(){
  python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$target"
  BOOTLOADER_ACTIVE=0
  sleep 1.5
}

readback_and_verify(){
  READBACK_TMP="$(mktemp /tmp/ywd1278-programmed-readback.XXXXXX.bin)"
  stm32flash -b 115200 -r "$READBACK_TMP" -S "$flash_base:$readback_bytes" "$device"
  chmod 0600 "$READBACK_TMP"
  rb="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" readback --readback "$READBACK_TMP")" || die "Programmed firmware readback did not match qualified artifact"
  printf '%s\n' "$rb" | grep -v '^FLASH_WRITTEN=' || true
  grep -q '^YWD1278_PROGRAMMED_READBACK=PASS$' <<<"$rb" || die "Programmed readback marker missing"
  PROGRAMMED_READBACK_SHA256="$(sha256sum "$READBACK_TMP" | awk '{print $1}')"
  [[ "$PROGRAMMED_READBACK_SHA256" == "$readback_sha" ]] || die "Readback digest changed after verification"
}

section "Product firmware program/readback gate"
if [[ "$identity" == "$expected_identity" ]]; then
  info "Exact qualified AX25R4 identity is already running; verifying programmed bytes without rewriting flash."
  enter_bootloader
  readback_and_verify
  restart_application
  FLASH_WRITTEN=NO
  echo "EXISTING_PRODUCT_FIRMWARE_VERIFIED=YES"
else
  warn "A main-flash write is about to be possible. The verified stock rollback backup is preserved at: $STOCK_BACKUP_DIR"
  confirm_exact "WRITE-FIRMWARE-NOW" "Write the exact qualified AX25R4 image now?" || die "Product flash cancelled"
  enter_bootloader
  stm32flash -b 115200 -w "$FIRMWARE" -v "$device"
  FLASH_WRITTEN=YES
  ok "Programmer write/verify completed; independently reading programmed bytes back now"
  readback_and_verify
  restart_application
fi

section "Exact runtime identity after programmed readback"
set +e
post="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$HARDWARE_DETECT" --device "$device" --config "$CONFIG" 2>&1)"
post_rc=$?
set -e
printf '%s\n' "$post"
[[ $post_rc -eq 0 ]] || die "Programmed bytes verified but runtime identity probe failed (rc=$post_rc)"
post_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$post" | tail -1)"
post_identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$post" | tail -1)"
[[ "$post_target" == "$target" ]] || die "Post-flash target mismatch"
[[ "$post_identity" == "$expected_identity" ]] || die "Post-flash identity does not exactly match qualified AX25R4 identity: $post_identity"
ok "Exact qualified AX25R4 runtime identity verified"

section "Write service-eligibility evidence"
rm -f "$eligibility_record"
elig="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" write-eligibility \
  --config "$CONFIG" \
  --firmware "$FIRMWARE" \
  --readback-sha256 "$PROGRAMMED_READBACK_SHA256" \
  --runtime-identity "$post_identity" \
  --stock-backup-dir "$STOCK_BACKUP_DIR" \
  --output "$eligibility_record")" || die "Could not write service eligibility evidence"
printf '%s\n' "$elig" | grep -v '^FLASH_WRITTEN=' || true
chmod 0600 "$eligibility_record"

check="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$PROFILE" check-eligibility \
  --config "$CONFIG" --firmware "$FIRMWARE" --record "$eligibility_record")" || die "Service eligibility record did not verify"
printf '%s\n' "$check" | grep -v '^FLASH_WRITTEN=' || true

section "Stage-F complete"
echo "YWD1278_PRODUCT_FIRMWARE_DEPLOY=PASS"
echo "TARGET_ID=$target"
echo "PRODUCT_FIRMWARE_SHA256=$actual_sha"
echo "PROGRAMMED_READBACK_SHA256=$PROGRAMMED_READBACK_SHA256"
echo "PRODUCT_RUNTIME_IDENTITY_VERIFIED=YES"
echo "STOCK_BACKUP_DIR=$STOCK_BACKUP_DIR"
echo "STOCK_ROLLBACK_VERIFIED=YES"
echo "OPTION_BYTES_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
echo "TX_ENABLED=NO"
echo "FLASH_WRITTEN=$FLASH_WRITTEN"
echo "SERVICE_ELIGIBLE=YES"
echo "SERVICE_ENABLED=NO"
echo "ELIGIBILITY_RECORD=$eligibility_record"
