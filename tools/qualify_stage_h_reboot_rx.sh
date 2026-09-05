#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPECTED_INSTALLED_COMMIT="2f5299e65add072fea6ee55a54dc421faf00c276"
EXPECTED_TARGET="mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
EXPECTED_IDENTITY="MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
EXPECTED_SHA="b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_SIZE=59892
VENV=/opt/ywd-1278/venv
SOURCE_ROOT=/opt/ywd-1278/source
CONFIG=/etc/ywd-1278/config.toml
SERVICE=ywd-1278.service
DEVICE=/dev/ttyAMA0
ELIGIBILITY=/var/lib/ywd-1278/firmware-ready.json
MARKER=/var/lib/ywd-1278/stage-h-reboot-before.json
FIRMWARE="$REPO_ROOT/firmware/out/0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1-7ff74ed-hse8m.bin"
TIMEOUT=120

while (($#)); do
  case "$1" in
    --timeout) TIMEOUT="${2:?missing --timeout value}"; shift ;;
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    -h|--help) echo "Usage: sudo bash tools/qualify_stage_h_reboot_rx.sh [--timeout 120] [--firmware FILE]"; exit 0 ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ "$TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] timeout must be a positive integer" >&2; exit 2; }
for path in "$VENV/bin/python" "$SOURCE_ROOT/installer/hardware-detect.sh" "$SOURCE_ROOT/firmware/product-ax25r4.json" "$SCRIPT_DIR/qualify_stage_g_reboot_live_rx.py" "$CONFIG" "$ELIGIBILITY" "$MARKER" /opt/ywd-1278/installed-commit /proc/sys/kernel/random/boot_id "$FIRMWARE"; do
  [[ -e "$path" ]] || { echo "[FAIL] required path missing: $path" >&2; exit 3; }
done

mapfile -t before < <("$VENV/bin/python" - "$MARKER" <<'PY'
import json,sys
with open(sys.argv[1],encoding='utf-8') as f: d=json.load(f)
assert d['schema']==1 and d['stage']=='H-reboot'
print(d['boot_id_before']); print(d['installed_commit']); print(d['main_pid_before']); print(d['kiss_port']); print(d['console_port']); print(d['pty'])
PY
)
boot_before="${before[0]:-}"
marker_commit="${before[1]:-}"
pre_pid="${before[2]:-}"
kiss_port="${before[3]:-}"
console_port="${before[4]:-}"
pty="${before[5]:-}"

boot_after="$(tr -d '[:space:]' </proc/sys/kernel/random/boot_id)"
[[ "$boot_before" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "[FAIL] invalid pre-reboot boot ID" >&2; exit 4; }
[[ "$boot_after" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "[FAIL] invalid current boot ID" >&2; exit 4; }
[[ "$boot_after" != "$boot_before" ]] || { echo "[FAIL] kernel boot ID did not change; an actual reboot has not been proven" >&2; exit 4; }
[[ "$marker_commit" == "$EXPECTED_INSTALLED_COMMIT" ]] || { echo "[FAIL] pre-reboot marker is for a different installed candidate" >&2; exit 4; }
installed_commit="$(tr -d '[:space:]' </opt/ywd-1278/installed-commit)"
[[ "$installed_commit" == "$EXPECTED_INSTALLED_COMMIT" ]] || { echo "[FAIL] installed commit changed across reboot" >&2; exit 4; }
sha="$(sha256sum "$FIRMWARE" | awk '{print $1}')"; size="$(stat -c '%s' "$FIRMWARE")"
[[ "$sha" == "$EXPECTED_SHA" && "$size" == "$EXPECTED_SIZE" ]] || { echo "[FAIL] exact AX25R4 artifact is not present for eligibility revalidation" >&2; exit 4; }

mapfile -t cfg < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print('true' if d.get('radio',{}).get('tx_enabled',False) is True else 'false')
print('true' if d.get('firmware',{}).get('allow_automatic_flash',False) is True else 'false')
print(d.get('radio',{}).get('frequency_mhz','')); print(d.get('radio',{}).get('device',''))
print(d.get('kiss',{}).get('listen','')); print(d.get('kiss',{}).get('port',''))
print(d.get('console',{}).get('listen','')); print(d.get('console',{}).get('port','')); print(d.get('console',{}).get('pty_link',''))
PY
)
[[ "${cfg[0]:-true}" == false ]] || { echo "[FAIL] TX enabled after reboot" >&2; exit 5; }
[[ "${cfg[1]:-true}" == false ]] || { echo "[FAIL] automatic flash enabled after reboot" >&2; exit 5; }
[[ "${cfg[2]:-}" == 145.05 || "${cfg[2]:-}" == 145.050 ]] || { echo "[FAIL] frequency changed after reboot" >&2; exit 5; }
[[ "${cfg[3]:-}" == "$DEVICE" ]] || { echo "[FAIL] UART changed after reboot" >&2; exit 5; }
[[ "${cfg[4]:-}" == 127.0.0.1 && "${cfg[5]:-}" == "$kiss_port" ]] || { echo "[FAIL] KISS endpoint changed after reboot" >&2; exit 5; }
[[ "${cfg[6]:-}" == 127.0.0.1 && "${cfg[7]:-}" == "$console_port" ]] || { echo "[FAIL] Telnet endpoint changed after reboot" >&2; exit 5; }
[[ "${cfg[8]:-}" == "$pty" ]] || { echo "[FAIL] PTY path changed after reboot" >&2; exit 5; }

readiness="$($VENV/bin/python -m ywd1278.install.readiness --config "$CONFIG")"; printf '%s\n' "$readiness"
grep -q '^YWD1278_INSTALL_RUNTIME_READINESS=READY$' <<<"$readiness" || { echo "[FAIL] runtime readiness is not READY after reboot" >&2; exit 5; }
eligibility="$($VENV/bin/python -m ywd1278.install.firmware_trust --profile "$SOURCE_ROOT/firmware/product-ax25r4.json" check-eligibility --config "$CONFIG" --firmware "$FIRMWARE" --record "$ELIGIBILITY")"; printf '%s\n' "$eligibility"
grep -q '^SERVICE_ELIGIBLE=YES$' <<<"$eligibility" || { echo "[FAIL] service eligibility did not survive/revalidate after reboot" >&2; exit 5; }

[[ "$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)" == enabled ]] || { echo "[FAIL] service did not remain enabled across reboot" >&2; exit 6; }
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] service did not auto-start after reboot" >&2; exit 6; }
auto_pid="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$auto_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] auto-started service has no MainPID" >&2; exit 6; }
[[ -e "$pty" ]] || { echo "[FAIL] PTY did not return automatically after reboot" >&2; exit 6; }
for port in "$kiss_port" "$console_port"; do
  "$VENV/bin/python" - "$port" <<'PY'
import socket,sys
port=int(sys.argv[1])
with socket.create_connection(('127.0.0.1',port),timeout=3): pass
print(f'POST_REBOOT_AUTO_LOOPBACK_PORT_{port}=PASS')
PY
done

echo "YWD1278_STAGE_H_REBOOT_AUTOSTART=PASS"
echo "BOOT_ID_CHANGED=YES"
echo "PRE_REBOOT_BOOT_ID=$boot_before"
echo "POST_REBOOT_BOOT_ID=$boot_after"
echo "PRE_REBOOT_MAIN_PID=$pre_pid"
echo "AUTO_STARTED_MAIN_PID=$auto_pid"
echo "SERVICE_ENABLED_AFTER_REBOOT=YES"
echo "SERVICE_ACTIVE_BEFORE_QUALIFIER_MUTATION=YES"
echo "PTY_AUTO_RETURN=PASS"
echo "TX_ENABLED=NO"
echo "AUTOMATIC_FLASH=NO"

echo "===== POST-REBOOT UART RELEASE / EXACT HAT IDENTITY ====="
systemctl stop "$SERVICE"
state="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
[[ "$state" == inactive || "$state" == failed || "$state" == unknown ]] || { echo "[FAIL] service did not stop after reboot" >&2; exit 7; }
[[ ! -e "$pty" ]] || { echo "[FAIL] PTY leaked after post-reboot stop" >&2; exit 7; }
if fuser "$DEVICE" >/dev/null 2>&1; then echo "[FAIL] UART ownership leaked after post-reboot stop" >&2; fuser -v "$DEVICE" >&2 || true; exit 7; fi

detect="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/hardware-detect.sh" --device "$DEVICE" --config "$CONFIG")"; printf '%s\n' "$detect"
detected_target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect" | tail -1)"
detected_identity="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$detect" | tail -1)"
[[ "$detected_target" == "$EXPECTED_TARGET" ]] || { echo "[FAIL] target mismatch after reboot" >&2; exit 7; }
[[ "$detected_identity" == "$EXPECTED_IDENTITY" ]] || { echo "[FAIL] exact AX25R4 identity mismatch after reboot" >&2; exit 7; }
echo "POST_REBOOT_UART_RELEASE=PASS"
echo "POST_REBOOT_EXACT_AX25R4_IDENTITY=PASS"

systemctl start "$SERVICE"
for _ in {1..50}; do [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active && -e "$pty" ]] && break; sleep 0.1; done
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] service did not restart after identity check" >&2; exit 8; }
[[ -e "$pty" ]] || { echo "[FAIL] PTY did not return after identity-check restart" >&2; exit 8; }
[[ "$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)" == enabled ]] || { echo "[FAIL] service lost enabled state" >&2; exit 8; }
restart_pid="$(systemctl show -p MainPID --value "$SERVICE")"
for port in "$kiss_port" "$console_port"; do
  "$VENV/bin/python" - "$port" <<'PY'
import socket,sys,time
port=int(sys.argv[1]); last=None
for _ in range(30):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1): pass
        print(f'POST_IDENTITY_RESTART_LOOPBACK_PORT_{port}=PASS'); raise SystemExit(0)
    except OSError as exc: last=exc; time.sleep(0.1)
raise SystemExit(f'port {port} did not return: {last}')
PY
done

echo "===== POST-REBOOT FRESH 145.050 RX ====="
"$VENV/bin/python" "$SCRIPT_DIR/qualify_stage_g_reboot_live_rx.py" --kiss-host 127.0.0.1 --kiss-port "$kiss_port" --console-host 127.0.0.1 --console-port "$console_port" --pty "$pty" --timeout "$TIMEOUT"
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] service not active after fresh RX" >&2; exit 9; }
[[ "$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)" == enabled ]] || { echo "[FAIL] service not enabled after fresh RX" >&2; exit 9; }

echo "===== STAGE H REBOOT QUALIFICATION COMPLETE ====="
echo "YWD1278_STAGE_H_REBOOT_RX=PASS"
echo "BOOT_ID_CHANGED=YES"
echo "SERVICE_AUTO_START=PASS"
echo "RUNTIME_READINESS_AFTER_REBOOT=PASS"
echo "SERVICE_ELIGIBILITY_AFTER_REBOOT=PASS"
echo "KISS_TELNET_PTY_AUTO_RETURN=PASS"
echo "UART_RELEASE_AFTER_REBOOT_STOP=PASS"
echo "EXACT_AX25R4_IDENTITY_AFTER_REBOOT=PASS"
echo "FRESH_LIVE_RX_145050=PASS"
echo "FRESH_TELNET_MHEARD_ADVANCE=PASS"
echo "FRESH_PTY_MHEARD_ADVANCE=PASS"
echo "SERVICE_ENABLED=YES"
echo "SERVICE_ACTIVE=YES"
echo "FINAL_MAIN_PID=$restart_pid"
echo "TX_ENABLED=NO"
echo "KISS_DATA_SENT=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED_BY_QUALIFIER=NO"
