#!/usr/bin/env bash
set -Eeuo pipefail

# 0I-P5 one-time persistent config bootstrap for older installed appliances.
#
# Older curl-installed configs may predate the [node]/[mailbox] tables entirely.
# This helper owns no service, UART, modem, KISS, frame, scheduler, retry,
# firmware, GPIO, or RF behavior. It only appends the exact disabled P5
# node/mailbox profile when BOTH tables are absent, validates the complete
# candidate through the installed product loaders, and atomically installs it.

INSTALL_ROOT=/opt/ywd-1278
VENV="$INSTALL_ROOT/venv"
CONFIG=/etc/ywd-1278/config.toml
STATE_DIR=/var/lib/ywd-1278
BACKUP_DIR="$STATE_DIR/config-backups"
EXPECTED_COMMIT=""
DRY_RUN=0

usage(){
  cat <<'EOF'
Usage:
  sudo ./installer/persistent-bbs-config-bootstrap.sh \
    --expected-installed-commit SHA

Options:
  --expected-installed-commit SHA  Exact installed source commit.
  --dry-run                        Print the bounded plan and perform zero writes,
                                   service changes, UART/modem access, or RF I/O.

This helper is only for an older persistent config where BOTH [node] and
[mailbox] are absent. It appends the exact disabled YWDNOD/mailbox profile.
It never enables node, mailbox, or TX and does not restart the service.
EOF
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

echo "===== YWD-1278 0I-P5 LEGACY NODE/MAILBOX CONFIG BOOTSTRAP ====="
echo "NODE_PROFILE=YWDNOD"
echo "MAILBOX_DATABASE=/var/lib/ywd-1278/mailbox.sqlite3"
echo "MAILBOX_PACLEN=128"
echo "NODE_ENABLED_AFTER=NO"
echo "MAILBOX_ENABLED_AFTER=NO"
echo "PERSISTENT_TX_ENABLED_AFTER=NO"
echo "SERVICE_MUTATION=NO"
echo "MODEM_UART_ACCESS=NO"
echo "RF_TRANSMITTED=NO"
echo "FIRMWARE_ACTION=NO"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "YWD1278_0I_P5_CONFIG_BOOTSTRAP_DRY_RUN=PASS"
  echo "PERSISTENT_CONFIG_MUTATED=NO"
  echo "SYSTEMD_MUTATED=NO"
  echo "MODEM_UART_OPENED=NO"
  echo "RF_TRANSMITTED=NO"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 3; }
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[FAIL] --expected-installed-commit must be a full lowercase SHA" >&2
  exit 3
}
for path in "$VENV/bin/python" "$CONFIG" "$INSTALL_ROOT/installed-commit"; do
  [[ -e "$path" ]] || { echo "[FAIL] required installed appliance path missing: $path" >&2; exit 4; }
done
installed_commit="$(tr -d '[:space:]' <"$INSTALL_ROOT/installed-commit")"
[[ "$installed_commit" == "$EXPECTED_COMMIT" ]] || {
  echo "[FAIL] installed source commit mismatch: installed=$installed_commit expected=$EXPECTED_COMMIT" >&2
  exit 4
}

mkdir -p "$BACKUP_DIR"
chmod 0750 "$BACKUP_DIR"
candidate="$(mktemp "$STATE_DIR/0i-p5-bootstrap.XXXXXX")"
trap 'rm -f "$candidate"' EXIT

"$VENV/bin/python" - "$CONFIG" "$candidate" <<'PY'
from pathlib import Path
import sys,tomllib
from ywd1278.service.appliance import load_product_packet_engine_config
from ywd1278.service.node_mailbox_config import load_product_node_mailbox_config

source=Path(sys.argv[1])
out=Path(sys.argv[2])
text=source.read_text(encoding='utf-8')
root=tomllib.loads(text)

has_node='node' in root
has_mailbox='mailbox' in root
if has_node != has_mailbox:
    raise SystemExit('refusing partial legacy state: [node] and [mailbox] must both be absent or both present')
if has_node:
    raise SystemExit('refusing bootstrap: [node] and [mailbox] already exist')

station=root.get('station',{})
radio=root.get('radio',{})
hardware=root.get('hardware',{})
firmware=root.get('firmware',{})
beacon=root.get('beacon',{})
forwarding=root.get('forwarding',{})
if station.get('callsign','').strip().upper() != 'KJ6YWD' or station.get('ssid') != 10:
    raise SystemExit('physical qualification requires station KJ6YWD-10')
if radio.get('tx_enabled') is not False:
    raise SystemExit('persistent TX must be disabled before config bootstrap')
frequency=radio.get('frequency_mhz')
if isinstance(frequency,bool) or not isinstance(frequency,(int,float)) or int(round(float(frequency)*1_000_000)) != 145_050_000:
    raise SystemExit('physical qualification requires 145.050 MHz')
if hardware.get('target') != 'mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021':
    raise SystemExit('physical qualification requires exact qualified HAT target')
if firmware.get('required_product') != 'YWD-1278' or firmware.get('allow_automatic_flash') is not False:
    raise SystemExit('firmware profile is not fail-closed')
if beacon.get('enabled') is not False:
    raise SystemExit('beacon must remain disabled')
if forwarding and forwarding.get('enabled') is not False:
    raise SystemExit('forwarding must remain disabled')

if text and not text.endswith('\n'):
    text += '\n'
text += '''\n[node]\nenabled = false\nalias = "YWDNOD"\nmax_sessions = 1\n\n[mailbox]\nenabled = false\ndatabase = "/var/lib/ywd-1278/mailbox.sqlite3"\npaclen = 128\ninfo = "YWD-1278 persistent packet BBS"\n'''
out.write_text(text,encoding='utf-8')

# Validate the complete candidate through the installed product loaders.
packet=load_product_packet_engine_config(out)
node=load_product_node_mailbox_config(out)
if packet.tx_enabled:
    raise SystemExit('bootstrap candidate unexpectedly enabled TX')
if node.node_enabled or node.mailbox_enabled:
    raise SystemExit('bootstrap candidate unexpectedly enabled node/mailbox')
if node.alias != 'YWDNOD' or node.max_sessions != 1:
    raise SystemExit('bootstrap node profile mismatch')
if str(node.mailbox_database) != '/var/lib/ywd-1278/mailbox.sqlite3' or node.mailbox_paclen != 128:
    raise SystemExit('bootstrap mailbox profile mismatch')
print('PERSISTENT_BBS_BOOTSTRAP_CANDIDATE_VALID=YES')
PY

backup="$BACKUP_DIR/config.toml.pre-0i-p5-bootstrap.$(date +%Y%m%d-%H%M%S)"
cp -a "$CONFIG" "$backup"
staged="$CONFIG.0i-p5-bootstrap.$$"
cp "$candidate" "$staged"
chown --reference="$CONFIG" "$staged"
chmod --reference="$CONFIG" "$staged"
mv -f "$staged" "$CONFIG"

# Revalidate the persistent file after atomic installation.
"$VENV/bin/python" - "$CONFIG" <<'PY'
from pathlib import Path
import sys
from ywd1278.service.appliance import load_product_packet_engine_config
from ywd1278.service.node_mailbox_config import load_product_node_mailbox_config
p=Path(sys.argv[1])
packet=load_product_packet_engine_config(p)
node=load_product_node_mailbox_config(p)
if packet.tx_enabled or node.node_enabled or node.mailbox_enabled:
    raise SystemExit('installed bootstrap config is not RX-safe')
if node.alias != 'YWDNOD' or node.max_sessions != 1:
    raise SystemExit('installed node profile mismatch')
if str(node.mailbox_database) != '/var/lib/ywd-1278/mailbox.sqlite3' or node.mailbox_paclen != 128:
    raise SystemExit('installed mailbox profile mismatch')
PY

echo "YWD1278_0I_P5_CONFIG_BOOTSTRAP=PASS"
echo "INSTALLED_COMMIT=$installed_commit"
echo "CONFIG_BACKUP=$backup"
echo "NODE_ENABLED=NO"
echo "MAILBOX_ENABLED=NO"
echo "PERSISTENT_TX_ENABLED=NO"
echo "SERVICE_MUTATED=NO"
echo "MODEM_UART_OPENED=NO"
echo "RF_TRANSMITTED=NO"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
