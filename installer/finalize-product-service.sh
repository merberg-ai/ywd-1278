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
PRODUCT_FIRMWARE=/var/lib/ywd-1278/product-firmware/qualified-ax25r4.bin
HARDWARE_RECORD=/var/lib/ywd-1278/firmware-hardware-qualified.json
ELIGIBILITY_RECORD=/var/lib/ywd-1278/firmware-ready.json
ENABLE_SERVICE="$SOURCE_ROOT/installer/enable-product-service.sh"
INSTALLED_COMMIT_FILE=/opt/ywd-1278/installed-commit

[[ -n "$YWD_LOG_FILE" ]] || init_log /var/log/ywd-1278/install.log
for path in "$VENV/bin/python" "$CONFIG" "$PROFILE" "$PRODUCT_FIRMWARE" "$HARDWARE_RECORD" "$ENABLE_SERVICE" "$INSTALLED_COMMIT_FILE"; do
  [[ -e "$path" ]] || die "Required finalization path missing: $path"
done

section "Validate final runtime configuration"
if capture_logged readiness "Final runtime readiness" \
    "$VENV/bin/python" -m ywd1278.install.readiness --config "$CONFIG"; then
  :
else
  rc=$?
  case "$rc" in
    10) die "Station configuration is still incomplete; packet service remains stopped" ;;
    20) die "Station configuration is unsafe or invalid; packet service remains stopped" ;;
    *) die "Runtime readiness failed unexpectedly (rc=$rc); packet service remains stopped" ;;
  esac
fi
grep -q '^YWD1278_INSTALL_RUNTIME_READINESS=READY$' <<<"$readiness" || die "Runtime READY marker missing"
ok "Station configuration is READY and RF transmit remains disabled"

section "Promote verified HAT evidence"
rm -f "$ELIGIBILITY_RECORD"
if ! capture_logged promote "Hardware-to-service eligibility promotion" \
    "$VENV/bin/python" -m ywd1278.install.hardware_trust --profile "$PROFILE" promote \
      --config "$CONFIG" --firmware "$PRODUCT_FIRMWARE" \
      --record "$HARDWARE_RECORD" --output "$ELIGIBILITY_RECORD"; then
  die "Verified HAT evidence could not be promoted to service eligibility"
fi
grep -q '^YWD1278_HARDWARE_PROMOTION=PASS$' <<<"$promote" || die "Hardware promotion marker missing"
grep -q '^SERVICE_ELIGIBLE=YES$' <<<"$promote" || die "Service eligibility marker missing"
chmod 0600 "$ELIGIBILITY_RECORD"

if ! capture_logged eligibility "Service eligibility recheck" \
    "$VENV/bin/python" -m ywd1278.install.firmware_trust --profile "$PROFILE" check-eligibility \
      --config "$CONFIG" --firmware "$PRODUCT_FIRMWARE" --record "$ELIGIBILITY_RECORD"; then
  die "Final service eligibility record did not revalidate"
fi
grep -q '^SERVICE_ELIGIBLE=YES$' <<<"$eligibility" || die "Eligibility recheck marker missing"
ok "Firmware and station configuration are jointly service-eligible"

section "Start RX-safe packet service"
installed_commit="$(tr -d '[:space:]' <"$INSTALLED_COMMIT_FILE")"
[[ "$installed_commit" =~ ^[0-9a-f]{40}$ ]] || die "Installed source is not pinned to an exact Git commit; refusing service activation"

if ! capture_logged activation "RX-safe product service activation" \
    bash "$ENABLE_SERVICE" --firmware "$PRODUCT_FIRMWARE" \
      --expected-installed-commit "$installed_commit" --config "$CONFIG"; then
  die "Packet service activation failed"
fi
grep -q '^YWD1278_STAGE_G_SERVICE_ACTIVATION=PASS$' <<<"$activation" || die "Service activation marker missing"
grep -q '^SERVICE_ACTIVE=YES$' <<<"$activation" || die "Service-active marker missing"
grep -q '^TX_ENABLED=NO$' <<<"$activation" || die "Service activation did not preserve TX-disabled state"
ok "YWD-1278 packet service is active in RX-safe mode"

mapfile -t endpoints < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1], 'rb') as f: d=tomllib.load(f)
print(f"{d.get('kiss',{}).get('listen','127.0.0.1')}:{d.get('kiss',{}).get('port',8001)}")
print(f"{d.get('console',{}).get('listen','127.0.0.1')}:{d.get('console',{}).get('port',8010)}")
print(d.get('console',{}).get('pty_link','/run/ywd-1278/tnc'))
PY
)
step "KISS: ${endpoints[0]:-127.0.0.1:8001}"
step "Telnet console: ${endpoints[1]:-127.0.0.1:8010}"
step "PTY: ${endpoints[2]:-/run/ywd-1278/tnc}"

record_marker "YWD1278_PRODUCT_FINALIZE=PASS"
record_marker "YWD1278_RUNTIME_CONFIG_READY=YES"
record_marker "SERVICE_ELIGIBLE=YES"
record_marker "SERVICE_ENABLED=YES"
record_marker "SERVICE_ACTIVE=YES"
record_marker "TX_ENABLED=NO"
record_marker "RF_TRANSMITTED=NO"
record_marker "FLASH_WRITTEN=NO"
