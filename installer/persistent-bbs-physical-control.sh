#!/usr/bin/env bash
set -Eeuo pipefail

# 0I-P5 bounded physical-staging control for the persistent packet BBS.
#
# This helper owns no modem/UART, KISS DATA, frame construction, channel access,
# scheduler, retry, firmware, GPIO, or RF path.  It only stages/revokes the
# [node]/[mailbox] persistent configuration around the already-qualified
# 0F-P9 product TX authority control.
#
# STAGE deliberately leaves radio.tx_enabled=false and ywd-1278.service stopped.
# The operator must separately invoke product-tx-control.sh enable, which owns
# the exact qualified 145.050 MHz / power-200 / live-firmware authorization.
# CLEANUP stops the service first, revokes TX through product-tx-control.sh
# disable, disables node/mailbox, and restores the service policy captured by
# STAGE.  If cleanup fails after TX revocation, it fails closed with TX disabled.

INSTALL_ROOT=/opt/ywd-1278
SOURCE_ROOT="$INSTALL_ROOT/source"
VENV="$INSTALL_ROOT/venv"
CONFIG=/etc/ywd-1278/config.toml
UNIT_SOURCE="$SOURCE_ROOT/systemd/ywd-1278.service"
UNIT_INSTALLED=/etc/systemd/system/ywd-1278.service
SERVICE=ywd-1278.service
STATE_DIR=/var/lib/ywd-1278
BACKUP_DIR="$STATE_DIR/config-backups"
STAGE_STATE="$STATE_DIR/0i-p5-persistent-bbs-stage.env"
TX_CONTROL="$SOURCE_ROOT/installer/product-tx-control.sh"
EXPECTED_COMMIT=""
ACTION=""
DRY_RUN=0

QUALIFIED_CALLSIGN=KJ6YWD
QUALIFIED_SSID=10
QUALIFIED_FREQUENCY_HZ=145050000
QUALIFIED_ALIAS=YWDNOD
QUALIFIED_MAILBOX_DB=/var/lib/ywd-1278/mailbox.sqlite3
QUALIFIED_MAILBOX_PACLEN=128

usage(){
  cat <<'EOF'
Usage:
  sudo ./installer/persistent-bbs-physical-control.sh stage \
    --expected-installed-commit SHA

  sudo /opt/ywd-1278/source/installer/persistent-bbs-physical-control.sh cleanup \
    --expected-installed-commit SHA

  ./installer/persistent-bbs-physical-control.sh status

Options:
  --expected-installed-commit SHA  Exact installed source commit. Required for
                                   stage and cleanup.
  --dry-run                        Print the bounded plan and perform zero file,
                                   systemd, UART, modem, or RF I/O.

STAGE changes only [node].enabled and [mailbox].enabled to true, while requiring
persistent TX to remain disabled. It stops the normal service and leaves it
stopped for the separate guarded 0F-P9 TX-enable operation.

CLEANUP stops the normal service, revokes persistent TX using the existing
0F-P9 control, changes only [node].enabled and [mailbox].enabled to false, then
restores the service active/enabled policy captured by STAGE.
EOF
}

[[ $# -gt 0 ]] || { usage >&2; exit 2; }
ACTION="$1"; shift
[[ "$ACTION" == stage || "$ACTION" == cleanup || "$ACTION" == status ]] || {
  echo "[FAIL] action must be stage, cleanup, or status" >&2
  exit 2
}
while (($#)); do
  case "$1" in
    --expected-installed-commit) EXPECTED_COMMIT="${2:?missing commit}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

print_plan(){
  echo "===== YWD-1278 0I-P5 PERSISTENT BBS PHYSICAL STAGING ====="
  echo "ACTION=${ACTION^^}"
  echo "STATION=$QUALIFIED_CALLSIGN-$QUALIFIED_SSID"
  echo "TX_FREQUENCY_HZ=$QUALIFIED_FREQUENCY_HZ"
  echo "NODE_ALIAS=$QUALIFIED_ALIAS"
  echo "MAILBOX_DATABASE=$QUALIFIED_MAILBOX_DB"
  echo "MAILBOX_PACLEN=$QUALIFIED_MAILBOX_PACLEN"
  echo "NODE_MAILBOX_CONFIG_ONLY=YES"
  echo "TX_ENABLE_OWNED_BY_0F_P9_CONTROL=YES"
  echo "DIRECT_KISS_INJECTION=NO"
  echo "NEW_SCHEDULER=NO"
  echo "NEW_TX_RETRY=NO"
  echo "FIRMWARE_ACTION=NO"
}
print_plan

if [[ $DRY_RUN -eq 1 ]]; then
  echo "YWD1278_0I_P5_BBS_CONTROL_DRY_RUN=PASS"
  echo "PERSISTENT_CONFIG_MUTATED=NO"
  echo "SYSTEMD_MUTATED=NO"
  echo "MODEM_UART_OPENED=NO"
  echo "RF_TRANSMITTED=NO"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

config_snapshot(){
  python3 - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1], 'rb') as f:
    d=tomllib.load(f)
r=d.get('radio',{})
n=d.get('node',{})
m=d.get('mailbox',{})
s=d.get('station',{})
print(f"CONFIG_STATION={s.get('callsign','')}-{s.get('ssid','')}")
print(f"CONFIG_TX_ENABLED={str(r.get('tx_enabled')).upper()}")
print(f"CONFIG_NODE_ENABLED={str(n.get('enabled')).upper()}")
print(f"CONFIG_MAILBOX_ENABLED={str(m.get('enabled')).upper()}")
print(f"CONFIG_NODE_ALIAS={n.get('alias','')}")
print(f"CONFIG_MAILBOX_DATABASE={m.get('database','')}")
print(f"CONFIG_MAILBOX_PACLEN={m.get('paclen','')}")
PY
}

if [[ "$ACTION" == status ]]; then
  [[ -f "$CONFIG" ]] || { echo "[FAIL] config missing: $CONFIG" >&2; exit 4; }
  config_snapshot
  echo "SERVICE_ACTIVE=$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  echo "SERVICE_ENABLED=$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
  if [[ -f "$INSTALL_ROOT/installed-commit" ]]; then
    echo "INSTALLED_COMMIT=$(tr -d '[:space:]' <"$INSTALL_ROOT/installed-commit")"
  else
    echo "INSTALLED_COMMIT=MISSING"
  fi
  echo "P4C2_STAGE_STATE=$([[ -f "$STAGE_STATE" ]] && echo PRESENT || echo ABSENT)"
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 3; }
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[FAIL] --expected-installed-commit must be a full lowercase SHA" >&2
  exit 3
}
for path in "$VENV/bin/python" "$CONFIG" "$UNIT_SOURCE" "$UNIT_INSTALLED" "$INSTALL_ROOT/installed-commit" "$TX_CONTROL"; do
  [[ -e "$path" ]] || { echo "[FAIL] required installed appliance path missing: $path" >&2; exit 4; }
done
installed_commit="$(tr -d '[:space:]' <"$INSTALL_ROOT/installed-commit")"
[[ "$installed_commit" == "$EXPECTED_COMMIT" ]] || {
  echo "[FAIL] installed source commit mismatch: installed=$installed_commit expected=$EXPECTED_COMMIT" >&2
  exit 4
}
cmp -s "$UNIT_SOURCE" "$UNIT_INSTALLED" || {
  echo "[FAIL] installed systemd unit differs from installed source" >&2
  exit 4
}
mkdir -p "$BACKUP_DIR"
chmod 0750 "$BACKUP_DIR"

render_candidate(){
  local enable="$1" output="$2"
  "$VENV/bin/python" - "$CONFIG" "$output" "$enable" <<'PY'
from pathlib import Path
import re,sys,tomllib
source=Path(sys.argv[1])
out=Path(sys.argv[2])
enabled=sys.argv[3] == 'true'
text=source.read_text(encoding='utf-8')

def replace_bool(text, table, key, value):
    table_re=re.compile(rf'(?ms)^\[{re.escape(table)}\]\s*$\n(?P<body>.*?)(?=^\[[^\n]+\]\s*$|\Z)')
    m=table_re.search(text)
    if m is None:
        raise SystemExit(f'missing [{table}] table')
    body=m.group('body')
    key_re=re.compile(rf'(?m)^(?P<indent>[ \t]*){re.escape(key)}[ \t]*=[ \t]*(?:true|false)(?P<comment>[ \t]*#.*)?$')
    hits=list(key_re.finditer(body))
    if len(hits) != 1:
        raise SystemExit(f'[{table}] must contain exactly one boolean {key} assignment')
    hit=hits[0]
    replacement=f"{hit.group('indent')}{key} = {'true' if value else 'false'}{hit.group('comment') or ''}"
    new_body=body[:hit.start()]+replacement+body[hit.end():]
    return text[:m.start('body')]+new_body+text[m.end('body'):]

text=replace_bool(text,'node','enabled',enabled)
text=replace_bool(text,'mailbox','enabled',enabled)
tomllib.loads(text)
out.write_text(text,encoding='utf-8')
PY
}

validate_candidate(){
  local candidate="$1" expect="$2"
  "$VENV/bin/python" - "$candidate" "$expect" <<'PY'
from pathlib import Path
import sys,tomllib
from ywd1278.service.appliance import load_product_packet_engine_config
from ywd1278.service.node_mailbox_config import load_product_node_mailbox_config

p=Path(sys.argv[1]); expect=sys.argv[2] == 'enabled'
packet=load_product_packet_engine_config(p)
node=load_product_node_mailbox_config(p)
with p.open('rb') as f: root=tomllib.load(f)
station=root.get('station',{})
radio=root.get('radio',{})
beacon=root.get('beacon',{})
forwarding=root.get('forwarding',{})
firmware=root.get('firmware',{})
hardware=root.get('hardware',{})

if station.get('callsign','').strip().upper() != 'KJ6YWD' or station.get('ssid') != 10:
    raise SystemExit('physical qualification requires station KJ6YWD-10')
if packet.frequency_hz != 145_050_000:
    raise SystemExit('physical qualification requires 145.050 MHz')
if packet.tx_enabled:
    raise SystemExit('BBS staging candidate must keep persistent TX disabled')
if hardware.get('target') != 'mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021':
    raise SystemExit('physical qualification requires exact qualified HAT target')
if firmware.get('required_product') != 'YWD-1278' or firmware.get('allow_automatic_flash') is not False:
    raise SystemExit('firmware profile is not fail-closed')
if beacon.get('enabled') is not False:
    raise SystemExit('beacon must remain disabled')
if forwarding and forwarding.get('enabled') is not False:
    raise SystemExit('forwarding must remain disabled')
if expect:
    if not node.node_enabled or not node.mailbox_enabled:
        raise SystemExit('node/mailbox staging candidate did not enable both services')
    if node.local is None or str(node.local) != 'KJ6YWD-10':
        raise SystemExit('node local identity mismatch')
    if node.alias != 'YWDNOD' or node.max_sessions != 1:
        raise SystemExit('node qualification profile mismatch')
    if str(node.mailbox_database) != '/var/lib/ywd-1278/mailbox.sqlite3':
        raise SystemExit('mailbox database path mismatch')
    if node.mailbox_paclen != 128:
        raise SystemExit('mailbox PACLEN mismatch')
else:
    if node.node_enabled or node.mailbox_enabled:
        raise SystemExit('cleanup candidate did not disable node/mailbox')
print('PERSISTENT_BBS_CONFIG_VALID=YES')
print(f'NODE_MAILBOX_ENABLED={"YES" if expect else "NO"}')
print('PERSISTENT_TX_ENABLED=NO')
print(f'STATION={station.get("callsign")}-{station.get("ssid")}')
print(f'TX_FREQUENCY_HZ={packet.frequency_hz}')
print(f'NODE_ALIAS={node.alias}')
print(f'MAILBOX_DATABASE={node.mailbox_database}')
print(f'MAILBOX_PACLEN={node.mailbox_paclen}')
PY
}

if [[ "$ACTION" == stage ]]; then
  [[ ! -e "$STAGE_STATE" ]] || {
    echo "[FAIL] an existing P5 stage state is present: $STAGE_STATE" >&2
    echo "[FAIL] run status/cleanup before staging again" >&2
    exit 5
  }
  current="$($VENV/bin/python - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print('1' if d.get('radio',{}).get('tx_enabled') is False else '0')
print('1' if d.get('node',{}).get('enabled') is False else '0')
print('1' if d.get('mailbox',{}).get('enabled') is False else '0')
PY
)"
  [[ "$current" == $'1\n1\n1' ]] || {
    echo "[FAIL] stage requires radio.tx_enabled=false, node.enabled=false, mailbox.enabled=false" >&2
    config_snapshot >&2 || true
    exit 5
  }

  candidate="$(mktemp "$STATE_DIR/0i-p5-bbs-config.XXXXXX")"
  trap 'rm -f "$candidate"' EXIT
  render_candidate true "$candidate"
  validate_candidate "$candidate" enabled

  service_was_active="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  service_was_enabled="$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" != active ]] || {
    echo "[FAIL] product service would not stop" >&2
    exit 6
  }

  backup="$BACKUP_DIR/config.toml.pre-0i-p5-stage.$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  rollback_armed=1
  rollback(){
    rc=$?
    if [[ ${rollback_armed:-0} -eq 1 ]]; then
      echo "[ROLLBACK] restoring pre-P5 persistent configuration" >&2
      restored="$CONFIG.0i-p5-restore.$$"
      cp "$backup" "$restored"
      chown --reference="$backup" "$restored"
      chmod --reference="$backup" "$restored"
      mv -f "$restored" "$CONFIG"
      if [[ "$service_was_enabled" == enabled ]]; then systemctl enable "$SERVICE" >/dev/null 2>&1 || true; else systemctl disable "$SERVICE" >/dev/null 2>&1 || true; fi
      if [[ "$service_was_active" == active ]]; then systemctl start "$SERVICE" >/dev/null 2>&1 || true; fi
      rm -f "$STAGE_STATE"
    fi
    exit "$rc"
  }
  trap rollback ERR INT TERM

  staged="$CONFIG.0i-p5-new.$$"
  cp "$candidate" "$staged"
  chown --reference="$CONFIG" "$staged"
  chmod --reference="$CONFIG" "$staged"
  mv -f "$staged" "$CONFIG"
  validate_candidate "$CONFIG" enabled >/dev/null

  {
    printf 'STATE_VERSION=1\n'
    printf 'INSTALLED_COMMIT=%q\n' "$installed_commit"
    printf 'CONFIG_BACKUP=%q\n' "$backup"
    printf 'SERVICE_WAS_ACTIVE=%q\n' "$service_was_active"
    printf 'SERVICE_WAS_ENABLED=%q\n' "$service_was_enabled"
  } >"$STAGE_STATE"
  chmod 0600 "$STAGE_STATE"

  rollback_armed=0
  trap - ERR INT TERM
  echo "YWD1278_0I_P5_PERSISTENT_BBS_STAGED=PASS"
  echo "INSTALLED_COMMIT=$installed_commit"
  echo "CONFIG_BACKUP=$backup"
  echo "NODE_MAILBOX_ENABLED=YES"
  echo "PERSISTENT_TX_ENABLED=NO"
  echo "SERVICE_ACTIVE=NO"
  echo "NEXT_STEP=RUN_EXISTING_0F_P9_TX_ENABLE_CONTROL"
  echo "MODEM_UART_OPENED=NO"
  echo "RF_TRANSMITTED=NO"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

# CLEANUP
[[ -f "$STAGE_STATE" ]] || {
  echo "[FAIL] no P5 stage state found: $STAGE_STATE" >&2
  echo "[FAIL] if TX may be enabled, revoke it first with product-tx-control.sh disable" >&2
  exit 5
}
# shellcheck disable=SC1090
source "$STAGE_STATE"
[[ "${STATE_VERSION:-}" == 1 ]] || { echo "[FAIL] unsupported P5 stage state" >&2; exit 5; }
[[ "${INSTALLED_COMMIT:-}" == "$installed_commit" ]] || {
  echo "[FAIL] installed commit changed since P5 stage; refusing automated cleanup" >&2
  exit 5
}
[[ "$installed_commit" == "$EXPECTED_COMMIT" ]] || {
  echo "[FAIL] expected commit does not match staged installed commit" >&2
  exit 5
}

systemctl stop "$SERVICE" >/dev/null 2>&1 || true
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" != active ]] || {
  echo "[FAIL] product service would not stop for cleanup" >&2
  exit 6
}

# Revoke persistent TX while the service is stopped.  The frozen 0F-P9 disable
# operation does not restart an inactive service and never performs firmware/RF I/O.
"$TX_CONTROL" disable --expected-installed-commit "$installed_commit"

candidate="$(mktemp "$STATE_DIR/0i-p5-bbs-cleanup.XXXXXX")"
trap 'rm -f "$candidate"' EXIT
render_candidate false "$candidate"
validate_candidate "$candidate" disabled
backup="$BACKUP_DIR/config.toml.pre-0i-p5-cleanup.$(date +%Y%m%d-%H%M%S)"
cp -a "$CONFIG" "$backup"
staged="$CONFIG.0i-p5-clean.$$"
cp "$candidate" "$staged"
chown --reference="$CONFIG" "$staged"
chmod --reference="$CONFIG" "$staged"
mv -f "$staged" "$CONFIG"
validate_candidate "$CONFIG" disabled >/dev/null

if [[ "${SERVICE_WAS_ENABLED:-}" == enabled ]]; then
  systemctl enable "$SERVICE" >/dev/null
else
  systemctl disable "$SERVICE" >/dev/null 2>&1 || true
fi
if [[ "${SERVICE_WAS_ACTIVE:-}" == active ]]; then
  systemctl start "$SERVICE"
  for _ in {1..50}; do
    [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] && break
    sleep 0.1
  done
  [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || {
    echo "[FAIL] RX-safe service did not restart after cleanup; TX remains disabled" >&2
    exit 8
  }
else
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
fi
rm -f "$STAGE_STATE"

echo "YWD1278_0I_P5_PERSISTENT_BBS_CLEANUP=PASS"
echo "INSTALLED_COMMIT=$installed_commit"
echo "CLEANUP_CONFIG_BACKUP=$backup"
echo "NODE_MAILBOX_ENABLED=NO"
echo "PERSISTENT_TX_ENABLED=NO"
echo "SERVICE_ACTIVE_AFTER_CLEANUP=$([[ "${SERVICE_WAS_ACTIVE:-}" == active ]] && echo YES || echo NO)"
echo "SERVICE_ENABLED_AFTER_CLEANUP=$([[ "${SERVICE_WAS_ENABLED:-}" == enabled ]] && echo YES || echo NO)"
echo "MAILBOX_DATABASE_PRESERVED=$QUALIFIED_MAILBOX_DB"
echo "MODEM_UART_OPENED=NO"
echo "RF_TRANSMITTED_BY_CLEANUP=NO"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
