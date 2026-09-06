#!/usr/bin/env bash
set -Eeuo pipefail

# 0F-P9 explicit persistent product TX authority control.
#
# This wrapper does not create frames, inject KISS DATA, own the modem/UART,
# flash firmware, manipulate option bytes, schedule transmissions, or retry TX.
# It only validates the installed product boundary, atomically changes the
# persistent TX authority bit (and qualified power on enable), and restarts the
# already-qualified product service.

SOURCE_ROOT=/opt/ywd-1278/source
INSTALL_ROOT=/opt/ywd-1278
VENV="$INSTALL_ROOT/venv"
CONFIG=/etc/ywd-1278/config.toml
SERVICE=ywd-1278.service
PROFILE="$SOURCE_ROOT/firmware/product-ax25r4.json"
HARDWARE_DETECT="$SOURCE_ROOT/installer/hardware-detect.sh"
UNIT_SOURCE="$SOURCE_ROOT/systemd/ywd-1278.service"
UNIT_INSTALLED=/etc/systemd/system/ywd-1278.service
STATE_DIR=/var/lib/ywd-1278
BACKUP_DIR="$STATE_DIR/config-backups"
EXPECTED_COMMIT=""
ACTION=""
AUTHORIZATION=""
ARM_VALUE=""
DRY_RUN=0

ENABLE_AUTHORIZATION="0F-P9-PERSISTENT-PRODUCT-TX-145050"
ENABLE_ARM_PHRASE="ENABLE-0F-P9-PERSISTENT-TX"
QUALIFIED_FREQUENCY_HZ=145050000
QUALIFIED_POWER=200

usage(){
  cat <<'EOF'
Usage:
  sudo /opt/ywd-1278/source/installer/product-tx-control.sh enable \
    --expected-installed-commit SHA \
    --authorize 0F-P9-PERSISTENT-PRODUCT-TX-145050

  sudo /opt/ywd-1278/source/installer/product-tx-control.sh disable

Options:
  --config FILE                   Override /etc/ywd-1278/config.toml.
  --expected-installed-commit SHA Required for enable; optional for disable.
  --authorize TOKEN               Exact enable authorization token.
  --arm PHRASE                    Non-interactive exact arm phrase. If omitted,
                                  enable prompts on the terminal.
  --dry-run                       Print the bounded plan and perform zero file,
                                  systemd, UART, modem, or RF I/O.

Enable is restricted to the already-qualified 145.050 MHz / power-200 product
profile and exact live AX25R4 firmware identity. Disable is intentionally less
restrictive so TX authority can always be revoked from a syntactically valid
configuration.
EOF
}

[[ $# -gt 0 ]] || { usage >&2; exit 2; }
ACTION="$1"; shift
[[ "$ACTION" == enable || "$ACTION" == disable ]] || { echo "[FAIL] action must be enable or disable" >&2; exit 2; }
while (($#)); do
  case "$1" in
    --config) CONFIG="${2:?missing --config value}"; shift ;;
    --expected-installed-commit) EXPECTED_COMMIT="${2:?missing commit}"; shift ;;
    --authorize) AUTHORIZATION="${2:?missing authorization}"; shift ;;
    --arm) ARM_VALUE="${2:?missing arm phrase}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

print_plan(){
  echo "===== YWD-1278 0F-P9 PERSISTENT PRODUCT TX CONTROL ====="
  echo "ACTION=${ACTION^^}"
  echo "TX_FREQUENCY_HZ=$QUALIFIED_FREQUENCY_HZ"
  echo "TX_POWER_ON_ENABLE=$QUALIFIED_POWER"
  echo "TX_ORIGIN=EXISTING_PRODUCT_CONVERSE_BACKEND_ONLY"
  echo "AUTOMATIC_TX_RETRY=NO_NEW_RETRY"
  echo "BEACON_ACTIVATION=NO"
  echo "FORWARDING_ACTIVATION=NO"
  echo "FIRMWARE_FLASH=NO"
  echo "OPTION_BYTES_WRITE=NO"
  echo "DIRECT_KISS_INJECTION=NO"
}
print_plan

if [[ $DRY_RUN -eq 1 ]]; then
  echo "YWD1278_0F_P9_TX_CONTROL_DRY_RUN=PASS"
  echo "PERSISTENT_CONFIG_MUTATED=NO"
  echo "SYSTEMD_MUTATED=NO"
  echo "MODEM_UART_OPENED=NO"
  echo "RF_TRANSMITTED=NO"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 3; }
for path in "$VENV/bin/python" "$CONFIG" "$PROFILE" "$HARDWARE_DETECT" "$UNIT_SOURCE" "$UNIT_INSTALLED" "$INSTALL_ROOT/installed-commit"; do
  [[ -e "$path" ]] || { echo "[FAIL] required installed appliance path missing: $path" >&2; exit 4; }
done

installed_commit="$(tr -d '[:space:]' <"$INSTALL_ROOT/installed-commit")"
if [[ -n "$EXPECTED_COMMIT" ]]; then
  [[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "[FAIL] expected commit must be a full lowercase SHA" >&2; exit 4; }
  [[ "$installed_commit" == "$EXPECTED_COMMIT" ]] || {
    echo "[FAIL] installed source commit mismatch: installed=$installed_commit expected=$EXPECTED_COMMIT" >&2
    exit 4
  }
fi
if [[ "$ACTION" == enable && -z "$EXPECTED_COMMIT" ]]; then
  echo "[FAIL] enable requires --expected-installed-commit" >&2
  exit 4
fi
cmp -s "$UNIT_SOURCE" "$UNIT_INSTALLED" || { echo "[FAIL] installed systemd unit differs from installed source" >&2; exit 4; }

mkdir -p "$BACKUP_DIR"
chmod 0750 "$BACKUP_DIR"
candidate="$(mktemp "$STATE_DIR/0f-p9-config.XXXXXX")"
cleanup_candidate(){ rm -f "$candidate"; }
trap cleanup_candidate EXIT

"$VENV/bin/python" -m ywd1278.install.tx_control prepare "$ACTION" --config "$CONFIG" --output "$candidate"

if [[ "$ACTION" == disable ]]; then
  backup="$BACKUP_DIR/config.toml.pre-0f-p9-disable.$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  staged="$CONFIG.0f-p9-new.$$"
  cp "$candidate" "$staged"
  chown --reference="$CONFIG" "$staged"
  chmod --reference="$CONFIG" "$staged"
  mv -f "$staged" "$CONFIG"

  active_before="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  if [[ "$active_before" == active ]]; then
    systemctl restart "$SERVICE" || {
      echo "[FAIL] service restart failed after TX was disabled; TX remains disabled in persistent config" >&2
      exit 8
    }
  fi
  echo "YWD1278_0F_P9_PERSISTENT_TX_DISABLED=PASS"
  echo "INSTALLED_COMMIT=$installed_commit"
  echo "PERSISTENT_TX_ENABLED=NO"
  echo "CONFIG_BACKUP=$backup"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

[[ "$AUTHORIZATION" == "$ENABLE_AUTHORIZATION" ]] || { echo "[FAIL] exact enable authorization token required" >&2; exit 5; }
if [[ -z "$ARM_VALUE" ]]; then
  printf 'Type exactly %s to enable persistent product TX: ' "$ENABLE_ARM_PHRASE"
  IFS= read -r ARM_VALUE
fi
[[ "$ARM_VALUE" == "$ENABLE_ARM_PHRASE" ]] || { echo "[FAIL] persistent TX enable not armed" >&2; exit 5; }

# The candidate must pass the exact installed product loaders before any
# persistent file or service state changes.
validation="$($VENV/bin/python -m ywd1278.install.tx_control validate --config "$candidate" --expect enabled)" || exit $?
printf '%s\n' "$validation"
grep -q '^PRODUCT_TX_CONFIG_VALID=YES$' <<<"$validation" || { echo "[FAIL] candidate product validation marker missing" >&2; exit 5; }
grep -q '^TX_FREQUENCY_HZ=145050000$' <<<"$validation" || { echo "[FAIL] candidate frequency not qualified" >&2; exit 5; }
grep -q '^TX_POWER=200$' <<<"$validation" || { echo "[FAIL] candidate power not qualified" >&2; exit 5; }

mapfile -t profile_state < <("$VENV/bin/python" - "$PROFILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p['target_id'])
print(p['expected_identity'])
PY
)
expected_target="${profile_state[0]:-}"
expected_identity="${profile_state[1]:-}"
[[ -n "$expected_target" && -n "$expected_identity" ]] || { echo "[FAIL] product firmware profile incomplete" >&2; exit 5; }

device="$($VENV/bin/python - "$candidate" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print(d['radio']['device'])
PY
)"
[[ "$device" == /dev/* && -e "$device" ]] || { echo "[FAIL] configured modem UART is unavailable: $device" >&2; exit 5; }

service_was_active="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
service_was_enabled="$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
systemctl stop "$SERVICE" >/dev/null 2>&1 || true
if fuser "$device" >/dev/null 2>&1; then
  echo "[FAIL] modem UART is still owned after service stop: $device" >&2
  fuser -v "$device" >&2 || true
  if [[ "$service_was_active" == active ]]; then systemctl start "$SERVICE" >/dev/null 2>&1 || true; fi
  exit 6
fi

set +e
detect="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$HARDWARE_DETECT" --device "$device" --config "$CONFIG" 2>&1)"
detect_rc=$?
set -e
printf '%s\n' "$detect"
if [[ $detect_rc -ne 0 ]]; then
  [[ "$service_was_active" == active ]] && systemctl start "$SERVICE" >/dev/null 2>&1 || true
  echo "[FAIL] exact live product HAT identity could not be established" >&2
  exit 6
fi
detected_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect" | tail -1)"
detected_identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$detect" | tail -1)"
if [[ "$detected_target" != "$expected_target" || "$detected_identity" != "$expected_identity" ]]; then
  [[ "$service_was_active" == active ]] && systemctl start "$SERVICE" >/dev/null 2>&1 || true
  echo "[FAIL] live HAT identity does not match exact qualified AX25R4 profile" >&2
  exit 6
fi

backup="$BACKUP_DIR/config.toml.pre-0f-p9-enable.$(date +%Y%m%d-%H%M%S)"
cp -a "$CONFIG" "$backup"
rollback_armed=1
rollback(){
  rc=$?
  if [[ ${rollback_armed:-0} -eq 1 ]]; then
    echo "[ROLLBACK] restoring pre-P9 persistent configuration" >&2
    restored="$CONFIG.0f-p9-restore.$$"
    cp "$backup" "$restored"
    chown --reference="$backup" "$restored"
    chmod --reference="$backup" "$restored"
    mv -f "$restored" "$CONFIG"
    if [[ "$service_was_enabled" == enabled ]]; then systemctl enable "$SERVICE" >/dev/null 2>&1 || true; else systemctl disable "$SERVICE" >/dev/null 2>&1 || true; fi
    if [[ "$service_was_active" == active ]]; then systemctl start "$SERVICE" >/dev/null 2>&1 || true; else systemctl stop "$SERVICE" >/dev/null 2>&1 || true; fi
  fi
  exit "$rc"
}
trap rollback ERR INT TERM

staged="$CONFIG.0f-p9-new.$$"
cp "$candidate" "$staged"
chown --reference="$CONFIG" "$staged"
chmod --reference="$CONFIG" "$staged"
mv -f "$staged" "$CONFIG"

# Revalidate the file actually installed at the persistent path.
"$VENV/bin/python" -m ywd1278.install.tx_control validate --config "$CONFIG" --expect enabled >/dev/null
systemctl daemon-reload
systemctl enable --now "$SERVICE"
for _ in {1..50}; do
  [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] && break
  sleep 0.1
done
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] product service did not become active" >&2; false; }
main_pid="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] systemd reports no live product daemon" >&2; false; }

rollback_armed=0
trap - ERR INT TERM

echo "YWD1278_0F_P9_PERSISTENT_TX_ENABLED=PASS"
echo "INSTALLED_COMMIT=$installed_commit"
echo "TARGET_ID=$detected_target"
echo "RUNTIME_IDENTITY_VERIFIED=YES"
echo "SERVICE_ENABLED=YES"
echo "SERVICE_ACTIVE=YES"
echo "MAIN_PID=$main_pid"
echo "TX_FREQUENCY_HZ=$QUALIFIED_FREQUENCY_HZ"
echo "TX_POWER=$QUALIFIED_POWER"
echo "PERSISTENT_TX_ENABLED=YES"
echo "CONFIG_BACKUP=$backup"
echo "AUTOMATIC_TX_RETRY=NO_NEW_RETRY"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
