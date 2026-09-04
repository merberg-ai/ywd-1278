#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-/opt/ywd-1278/source}"
VENV=/opt/ywd-1278/venv
CONFIG=/etc/ywd-1278/config.toml
PROFILE="$SOURCE_ROOT/firmware/product-ax25r4.json"
ELIGIBILITY=/var/lib/ywd-1278/firmware-ready.json
HARDWARE_DETECT="$SOURCE_ROOT/installer/hardware-detect.sh"
UNIT_SOURCE="$SOURCE_ROOT/systemd/ywd-1278.service"
UNIT_INSTALLED=/etc/systemd/system/ywd-1278.service
FIRMWARE=""
EXPECTED_COMMIT=""

usage(){
  cat <<'EOF'
Usage:
  sudo ./installer/enable-product-service.sh --firmware FILE \
    --expected-installed-commit SHA [--config FILE]

Stage-G service activation gate.  It revalidates the Stage-F eligibility record,
exact live AX25R4 identity, installed source/unit identity, and no-TX/no-auto-
flash configuration before systemd may enable/start ywd-1278.service.
EOF
}

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 2; }

while (($#)); do
  case "$1" in
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    --expected-installed-commit) EXPECTED_COMMIT="${2:?missing --expected-installed-commit value}"; shift ;;
    --config) CONFIG="${2:?missing --config value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

for path in "$VENV/bin/python" "$PROFILE" "$ELIGIBILITY" "$HARDWARE_DETECT" "$UNIT_SOURCE" "$UNIT_INSTALLED" "$CONFIG"; do
  [[ -e "$path" ]] || { echo "[FAIL] required installed appliance path missing: $path" >&2; exit 3; }
done
[[ -n "$FIRMWARE" && -f "$FIRMWARE" ]] || { echo "[FAIL] --firmware must name the exact Stage-F AX25R4 artifact" >&2; exit 3; }
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "[FAIL] --expected-installed-commit must be a full lowercase Git SHA" >&2; exit 3; }

installed_commit="$(tr -d '[:space:]' </opt/ywd-1278/installed-commit 2>/dev/null || true)"
[[ "$installed_commit" == "$EXPECTED_COMMIT" ]] || {
  echo "[FAIL] installed source commit mismatch: installed=$installed_commit expected=$EXPECTED_COMMIT" >&2
  exit 4
}

cmp -s "$UNIT_SOURCE" "$UNIT_INSTALLED" || {
  echo "[FAIL] installed systemd unit differs from the qualified installed source" >&2
  exit 4
}

mapfile -t config_state < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print(d.get('hardware',{}).get('target',''))
print(d.get('radio',{}).get('device',''))
print('true' if d.get('radio',{}).get('tx_enabled',False) is True else 'false')
print('true' if d.get('firmware',{}).get('allow_automatic_flash',False) is True else 'false')
print(d.get('radio',{}).get('frequency_mhz',''))
PY
)
target="${config_state[0]:-}"
device="${config_state[1]:-}"
tx_enabled="${config_state[2]:-true}"
auto_flash="${config_state[3]:-true}"
frequency_mhz="${config_state[4]:-}"
[[ "$tx_enabled" == false ]] || { echo "[FAIL] TX must remain disabled for Stage G" >&2; exit 5; }
[[ "$auto_flash" == false ]] || { echo "[FAIL] automatic flash must remain disabled for Stage G" >&2; exit 5; }
[[ "$frequency_mhz" == "145.05" || "$frequency_mhz" == "145.050" ]] || { echo "[FAIL] Stage G rehearsal requires 145.050 MHz" >&2; exit 5; }
[[ -n "$device" && -e "$device" ]] || { echo "[FAIL] configured UART does not exist: $device" >&2; exit 5; }

profile_target="$($VENV/bin/python - "$PROFILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p['target_id'])
print(p['expected_identity'])
PY
)"
expected_target="$(sed -n '1p' <<<"$profile_target")"
expected_identity="$(sed -n '2p' <<<"$profile_target")"
[[ "$target" == "$expected_target" ]] || { echo "[FAIL] configured target does not match product AX25R4 profile" >&2; exit 5; }

eligibility_out="$($VENV/bin/python -m ywd1278.install.firmware_trust \
  --profile "$PROFILE" check-eligibility \
  --config "$CONFIG" --firmware "$FIRMWARE" --record "$ELIGIBILITY")" || {
    echo "[FAIL] Stage-F SERVICE-ELIGIBLE record no longer validates" >&2
    exit 6
  }
printf '%s\n' "$eligibility_out"
grep -q '^SERVICE_ELIGIBLE=YES$' <<<"$eligibility_out" || { echo "[FAIL] eligibility marker missing" >&2; exit 6; }

echo "===== STAGE G LIVE HAT IDENTITY RECHECK ====="
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
if fuser "$device" >/dev/null 2>&1; then
  echo "[FAIL] UART is already owned before service activation: $device" >&2
  fuser -v "$device" >&2 || true
  exit 7
fi

set +e
detect="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$HARDWARE_DETECT" --device "$device" --config "$CONFIG" 2>&1)"
detect_rc=$?
set -e
printf '%s\n' "$detect"
[[ $detect_rc -eq 0 ]] || { echo "[FAIL] exact supported HAT identity could not be re-established" >&2; exit 7; }
detected_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect" | tail -1)"
detected_identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$detect" | tail -1)"
[[ "$detected_target" == "$expected_target" ]] || { echo "[FAIL] live target mismatch" >&2; exit 7; }
[[ "$detected_identity" == "$expected_identity" ]] || { echo "[FAIL] live firmware identity is not exact qualified AX25R4" >&2; exit 7; }

systemctl daemon-reload
systemctl enable --now ywd-1278.service
for _ in {1..50}; do
  [[ "$(systemctl is-active ywd-1278.service 2>/dev/null || true)" == active ]] && break
  sleep 0.1
done
[[ "$(systemctl is-active ywd-1278.service 2>/dev/null || true)" == active ]] || {
  echo "[FAIL] ywd-1278.service did not become active" >&2
  systemctl status --no-pager ywd-1278.service >&2 || true
  exit 8
}
main_pid="$(systemctl show -p MainPID --value ywd-1278.service)"
[[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] systemd reports no live daemon MainPID" >&2; exit 8; }

echo "YWD1278_STAGE_G_SERVICE_ACTIVATION=PASS"
echo "INSTALLED_COMMIT=$installed_commit"
echo "TARGET_ID=$detected_target"
echo "RUNTIME_IDENTITY_VERIFIED=YES"
echo "SERVICE_ELIGIBLE=YES"
echo "SERVICE_ENABLED=YES"
echo "SERVICE_ACTIVE=YES"
echo "MAIN_PID=$main_pid"
echo "TX_ENABLED=NO"
echo "AUTOMATIC_FLASH=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
