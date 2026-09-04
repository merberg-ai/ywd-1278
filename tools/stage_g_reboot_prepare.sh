#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 2; }

EXPECTED_INSTALLED_COMMIT="5cb6e072c61d00376c1c46db7832912d71cace26"
VENV=/opt/ywd-1278/venv
CONFIG=/etc/ywd-1278/config.toml
SERVICE=ywd-1278.service
PTY=/run/ywd-1278/tnc
MARKER=/var/lib/ywd-1278/stage-g-reboot-before.json

for path in "$VENV/bin/python" "$CONFIG" /opt/ywd-1278/installed-commit /proc/sys/kernel/random/boot_id; do
  [[ -e "$path" ]] || { echo "[FAIL] required path missing: $path" >&2; exit 3; }
done

installed_commit="$(tr -d '[:space:]' </opt/ywd-1278/installed-commit)"
[[ "$installed_commit" == "$EXPECTED_INSTALLED_COMMIT" ]] || {
  echo "[FAIL] installed commit is not the physically qualified Stage-G candidate" >&2
  echo "INSTALLED_COMMIT=$installed_commit" >&2
  echo "EXPECTED_INSTALLED_COMMIT=$EXPECTED_INSTALLED_COMMIT" >&2
  exit 4
}

[[ "$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)" == enabled ]] || { echo "[FAIL] service is not enabled before reboot" >&2; exit 4; }
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] service is not active before reboot" >&2; exit 4; }
main_pid="$(systemctl show -p MainPID --value "$SERVICE")"
[[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] service has no live MainPID before reboot" >&2; exit 4; }
[[ -e "$PTY" ]] || { echo "[FAIL] PTY is missing before reboot: $PTY" >&2; exit 4; }

mapfile -t cfg < <("$VENV/bin/python" - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print('true' if d.get('radio',{}).get('tx_enabled',False) is True else 'false')
print('true' if d.get('firmware',{}).get('allow_automatic_flash',False) is True else 'false')
print(d.get('radio',{}).get('frequency_mhz',''))
print(d.get('radio',{}).get('device',''))
print(d.get('kiss',{}).get('listen',''))
print(d.get('kiss',{}).get('port',''))
print(d.get('console',{}).get('listen',''))
print(d.get('console',{}).get('port',''))
print(d.get('console',{}).get('pty_link',''))
PY
)

[[ "${cfg[0]:-true}" == false ]] || { echo "[FAIL] TX must remain disabled" >&2; exit 5; }
[[ "${cfg[1]:-true}" == false ]] || { echo "[FAIL] automatic flash must remain disabled" >&2; exit 5; }
[[ "${cfg[2]:-}" == 145.05 || "${cfg[2]:-}" == 145.050 ]] || { echo "[FAIL] frequency must remain 145.050 MHz" >&2; exit 5; }
[[ "${cfg[3]:-}" == /dev/ttyAMA0 ]] || { echo "[FAIL] unexpected UART: ${cfg[3]:-}" >&2; exit 5; }
[[ "${cfg[4]:-}" == 127.0.0.1 ]] || { echo "[FAIL] KISS must remain loopback-only" >&2; exit 5; }
[[ "${cfg[6]:-}" == 127.0.0.1 ]] || { echo "[FAIL] Telnet must remain loopback-only" >&2; exit 5; }
[[ "${cfg[8]:-}" == "$PTY" ]] || { echo "[FAIL] unexpected PTY link: ${cfg[8]:-}" >&2; exit 5; }

readiness="$($VENV/bin/python -m ywd1278.install.readiness --config "$CONFIG")"
printf '%s\n' "$readiness"
grep -q '^YWD1278_INSTALL_RUNTIME_READINESS=READY$' <<<"$readiness" || { echo "[FAIL] runtime readiness is not READY" >&2; exit 5; }

for port in "${cfg[5]}" "${cfg[7]}"; do
  "$VENV/bin/python" - "$port" <<'PY'
import socket,sys
port=int(sys.argv[1])
with socket.create_connection(('127.0.0.1',port),timeout=3):
    pass
print(f'PRE_REBOOT_LOOPBACK_PORT_{port}=PASS')
PY
done

boot_id="$(tr -d '[:space:]' </proc/sys/kernel/random/boot_id)"
[[ "$boot_id" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "[FAIL] invalid kernel boot ID" >&2; exit 6; }

"$VENV/bin/python" - "$MARKER" "$boot_id" "$installed_commit" "$main_pid" "${cfg[5]}" "${cfg[7]}" <<'PY'
import json,sys,time
path,boot_id,commit,pid,kiss_port,console_port=sys.argv[1:]
d={
  'schema':1,
  'stage':'G-reboot',
  'prepared_unix_ns':time.time_ns(),
  'boot_id_before':boot_id,
  'installed_commit':commit,
  'service_enabled_before':True,
  'service_active_before':True,
  'main_pid_before':int(pid),
  'frequency_hz':145050000,
  'tx_enabled':False,
  'automatic_flash_enabled':False,
  'kiss_host':'127.0.0.1',
  'kiss_port':int(kiss_port),
  'console_host':'127.0.0.1',
  'console_port':int(console_port),
  'pty':'/run/ywd-1278/tnc',
}
with open(path,'w',encoding='utf-8') as f:
    json.dump(d,f,indent=2,sort_keys=True)
    f.write('\n')
PY
chmod 0600 "$MARKER"

echo "YWD1278_STAGE_G_REBOOT_PREPARE=PASS"
echo "PRE_REBOOT_BOOT_ID=$boot_id"
echo "PRE_REBOOT_MAIN_PID=$main_pid"
echo "INSTALLED_COMMIT=$installed_commit"
echo "SERVICE_ENABLED=YES"
echo "SERVICE_ACTIVE=YES"
echo "TX_ENABLED=NO"
echo "AUTOMATIC_FLASH=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
echo "REBOOT_MARKER=$MARKER"
echo "REBOOT_EXECUTED_BY_THIS_SCRIPT=NO"
