#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-/opt/ywd-1278/source}"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root

VENV=/opt/ywd-1278/venv
CONFIG=/etc/ywd-1278/config.toml
PROFILE="$SOURCE_ROOT/firmware/product-ax25r4.json"
HARDWARE_RECORD=/var/lib/ywd-1278/firmware-hardware-qualified.json
INSTALL_COMPLETE=/var/lib/ywd-1278/install-complete
RUN_SETUP=1
BUILD_USER="${YWD1278_BUILD_USER:-${SUDO_USER:-}}"
ALLOW_CANDIDATE_RELEASE=0

usage(){
  cat <<'EOF'
Usage: sudo ./installer/continue-install.sh [options]
  --setup                       Run interactive station setup (default)
  --no-setup                    Preserve existing station configuration
  --build-user USER             Non-root account used to build firmware
  --allow-candidate-release     Permit the supported HAT GPIO release fallback
EOF
}

while (($#)); do
  case "$1" in
    --setup) RUN_SETUP=1 ;;
    --no-setup) RUN_SETUP=0 ;;
    --build-user) BUILD_USER="${2:?missing --build-user value}"; shift ;;
    --allow-candidate-release) ALLOW_CANDIDATE_RELEASE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

[[ -n "$YWD_LOG_FILE" ]] || init_log /var/log/ywd-1278/install.log
for path in "$VENV/bin/python" "$CONFIG" "$PROFILE" "$SOURCE_ROOT/installer/setup-hat.sh" "$SOURCE_ROOT/installer/setup.sh" "$SOURCE_ROOT/installer/finalize-product-service.sh"; do
  [[ -e "$path" ]] || die "Required continuation path missing: $path"
done

section "Confirm radio UART readiness"
if ! capture_logged audit "Interactive continuation UART audit" bash "$SOURCE_ROOT/installer/platform.sh" audit; then
  die "Raspberry Pi UART audit failed"
fi
grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" || die "Radio UART is not ready; reboot/platform repair must complete before HAT setup"
grep -q '^SERIAL_CONSOLE_PRESENT=NO$' <<<"$audit" || die "Serial console still owns the radio UART"
ok "Radio UART is ready"

stage "3/4  Prepare the radio HAT"
hat_args=()
[[ $ALLOW_CANDIDATE_RELEASE -eq 0 ]] || hat_args+=(--allow-candidate-release)
YWD1278_SOURCE_ROOT="$SOURCE_ROOT" YWD1278_BUILD_USER="$BUILD_USER" \
  bash "$SOURCE_ROOT/installer/setup-hat.sh" "${hat_args[@]}"

mapfile -t hat_state < <("$VENV/bin/python" - "$HARDWARE_RECORD" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding='utf-8'))
print(r.get('target_id',''))
print(r.get('runtime_identity',''))
PY
)
DETECTED_TARGET="${hat_state[0]:-}"
DETECTED_IDENTITY="${hat_state[1]:-}"
[[ -n "$DETECTED_TARGET" && -n "$DETECTED_IDENTITY" ]] || die "Verified HAT record is incomplete"

stage "4/4  Configure and start the appliance"
if [[ $RUN_SETUP -eq 1 ]]; then
  section "Configure station"
  YWD1278_SOURCE_ROOT="$SOURCE_ROOT" \
  YWD1278_DETECTED_TARGET="$DETECTED_TARGET" \
  YWD1278_DETECTED_IDENTITY="$DETECTED_IDENTITY" \
  YWD1278_FIRMWARE_CLASS="YWD1278" \
  YWD1278_FIRMWARE_DESCRIPTION="Qualified YWD-1278 AX25R4 packet firmware" \
    bash "$SOURCE_ROOT/installer/setup.sh"
else
  info "Interactive station setup skipped by request; existing configuration will be validated"
fi

section "Framework verification"
run_logged "Checking installed runtime" "$VENV/bin/ywd1278d" --config "$CONFIG" --framework-self-test || die "Installed runtime self-test failed"

set +e
capture_logged readiness "Post-setup runtime readiness" "$VENV/bin/python" -m ywd1278.install.readiness --config "$CONFIG"
readiness_rc=$?
set -e

case "$readiness_rc" in
  0)
    ok "Station configuration is READY"
    bash "$SOURCE_ROOT/installer/finalize-product-service.sh"
    runtime_ready=YES
    service_enabled=YES
    ;;
  10)
    if [[ $RUN_SETUP -eq 1 ]]; then
      die "Interactive station setup finished but runtime configuration is still incomplete"
    fi
    warn "Existing station configuration is safely incomplete; packet service remains stopped"
    systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
    runtime_ready=NO
    service_enabled=NO
    ;;
  20)
    die "Station configuration is unsafe or invalid; packet service remains stopped"
    ;;
  *)
    die "Runtime readiness failed unexpectedly (rc=$readiness_rc); packet service remains stopped"
    ;;
esac

install -d -m 0755 "$(dirname -- "$INSTALL_COMPLETE")"
date -u +'%Y-%m-%dT%H:%M:%SZ' >"$INSTALL_COMPLETE"

section "Installation complete"
ok "YWD-1278 software and radio HAT are installed"
ok "Exact AX25R4 firmware and rollback evidence are verified"
if [[ "$service_enabled" == YES ]]; then
  ok "Packet service is active with RF transmit disabled"
else
  warn "Packet service is stopped until station configuration is completed"
fi
info "Config: $CONFIG"
info "Installation log: ${YWD_LOG_FILE:-/var/log/ywd-1278/install.log}"

record_marker "YWD1278_INSTALL=PASS"
record_marker "YWD1278_HAT_READY=YES"
record_marker "YWD1278_RUNTIME_CONFIG_READY=$runtime_ready"
record_marker "SERVICE_ENABLED=$service_enabled"
record_marker "RF_TRANSMITTED=NO"
