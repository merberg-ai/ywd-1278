#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 2; }

SOURCE_ROOT=/opt/ywd-1278/source
VENV=/opt/ywd-1278/venv
CONFIG=/etc/ywd-1278/config.toml
SERVICE=ywd-1278.service
PTY_LINK=/run/ywd-1278/tnc
DEVICE=/dev/ttyAMA0
TIMEOUT=120

while (($#)); do
  case "$1" in
    --timeout) TIMEOUT="${2:?missing --timeout value}"; shift ;;
    --device) DEVICE="${2:?missing --device value}"; shift ;;
    -h|--help)
      echo "Usage: sudo bash tools/qualify_stage_g_systemd_rx.sh [--timeout 120] [--device /dev/ttyAMA0]"
      exit 0
      ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ "$TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] timeout must be a positive integer" >&2; exit 2; }
for path in "$VENV/bin/python" "$CONFIG" "$SOURCE_ROOT/tools/qualify_stage_g_live_rx.py"; do
  [[ -e "$path" ]] || { echo "[FAIL] installed appliance path missing: $path" >&2; exit 3; }
done
[[ -e "$DEVICE" ]] || { echo "[FAIL] modem UART missing: $DEVICE" >&2; exit 3; }

assert_active(){
  [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || {
    echo "[FAIL] $SERVICE is not active" >&2
    systemctl status --no-pager "$SERVICE" >&2 || true
    exit 4
  }
  for _ in {1..50}; do
    [[ -e "$PTY_LINK" ]] && return 0
    sleep 0.1
  done
  echo "[FAIL] PTY link did not appear while service is active: $PTY_LINK" >&2
  exit 4
}

assert_stopped(){
  local state
  state="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  [[ "$state" == inactive || "$state" == failed || "$state" == unknown ]] || {
    echo "[FAIL] service did not stop cleanly; state=$state" >&2
    exit 5
  }
  [[ ! -e "$PTY_LINK" ]] || { echo "[FAIL] PTY link leaked after stop: $PTY_LINK" >&2; exit 5; }
  if fuser "$DEVICE" >/dev/null 2>&1; then
    echo "[FAIL] UART ownership leaked after stop: $DEVICE" >&2
    fuser -v "$DEVICE" >&2 || true
    exit 5
  fi
}

mapfile -t cfg < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print('true' if d.get('radio',{}).get('tx_enabled',False) is True else 'false')
print('true' if d.get('firmware',{}).get('allow_automatic_flash',False) is True else 'false')
print(d.get('radio',{}).get('frequency_mhz',''))
print(d.get('kiss',{}).get('listen','127.0.0.1'))
print(d.get('kiss',{}).get('port',8001))
print(d.get('console',{}).get('listen','127.0.0.1'))
print(d.get('console',{}).get('port',8010))
print(d.get('console',{}).get('pty_link','/run/ywd-1278/tnc'))
PY
)
[[ "${cfg[0]:-true}" == false ]] || { echo "[FAIL] TX must remain disabled" >&2; exit 6; }
[[ "${cfg[1]:-true}" == false ]] || { echo "[FAIL] automatic flash must remain disabled" >&2; exit 6; }
[[ "${cfg[2]:-}" == 145.05 || "${cfg[2]:-}" == 145.050 ]] || { echo "[FAIL] frequency must be 145.050 MHz" >&2; exit 6; }
[[ "${cfg[3]:-}" == 127.0.0.1 ]] || { echo "[FAIL] Stage G requires loopback KISS" >&2; exit 6; }
[[ "${cfg[5]:-}" == 127.0.0.1 ]] || { echo "[FAIL] Stage G requires loopback Telnet" >&2; exit 6; }
[[ "${cfg[7]:-}" == "$PTY_LINK" ]] || { echo "[FAIL] Stage G requires PTY $PTY_LINK" >&2; exit 6; }

kiss_port="${cfg[4]:-8001}"
console_port="${cfg[6]:-8010}"

echo "===== STAGE G SYSTEMD STOP / SIGTERM ====="
old_pid="$(systemctl show -p MainPID --value "$SERVICE" 2>/dev/null || true)"
systemctl stop "$SERVICE"
assert_stopped
echo "SYSTEMD_STOP=PASS"
echo "SIGTERM_CLEANUP=PASS"
echo "PTY_CLEANUP=PASS"
echo "UART_RELEASE=PASS"
[[ "$old_pid" =~ ^[0-9]+$ ]] && echo "STOPPED_MAIN_PID=$old_pid"

echo "===== STAGE G SYSTEMD START ====="
systemctl start "$SERVICE"
assert_active
start_pid="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$start_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] no MainPID after start" >&2; exit 7; }
echo "SYSTEMD_START=PASS"
echo "START_MAIN_PID=$start_pid"

echo "===== STAGE G SYSTEMD RESTART ====="
systemctl restart "$SERVICE"
assert_active
restart_pid="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$restart_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] no MainPID after restart" >&2; exit 7; }
[[ "$restart_pid" != "$start_pid" ]] || { echo "[FAIL] restart did not replace daemon process" >&2; exit 7; }
echo "SYSTEMD_RESTART=PASS"
echo "RESTART_MAIN_PID=$restart_pid"

for port in "$kiss_port" "$console_port"; do
  "$VENV/bin/python" - "$port" <<'PY'
import socket,sys
port=int(sys.argv[1])
with socket.create_connection(('127.0.0.1',port),timeout=3):
    pass
print(f'LOOPBACK_PORT_{port}=PASS')
PY
done

echo "===== STAGE G LIVE 145.050 RX ====="
"$VENV/bin/python" "$SOURCE_ROOT/tools/qualify_stage_g_live_rx.py" \
  --kiss-host 127.0.0.1 --kiss-port "$kiss_port" \
  --console-host 127.0.0.1 --console-port "$console_port" \
  --pty "$PTY_LINK" --timeout "$TIMEOUT"

assert_active

echo "===== STAGE G RX-ONLY REHEARSAL COMPLETE ====="
echo "YWD1278_STAGE_G_EXISTING_PI_RX=PASS"
echo "SERVICE_ENABLED=$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
echo "SERVICE_ACTIVE=YES"
echo "SYSTEMD_STOP_START_RESTART_SIGTERM=PASS"
echo "LIVE_RX_145050=PASS"
echo "KISS_RX=PASS"
echo "TELNET_MHEARD=PASS"
echo "PTY_MHEARD=PASS"
echo "TX_ENABLED=NO"
echo "KISS_DATA_SENT=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED_BY_QUALIFIER=NO"
echo "REBOOT_QUALIFICATION=PENDING"
