#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
banner
section "Initial station configuration"

SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG_DIR=/etc/ywd-1278
CONFIG_FILE="$CONFIG_DIR/config.toml"
EXAMPLE="$SOURCE_ROOT/config/ywd-1278.example.toml"
TARGETS="$SOURCE_ROOT/firmware/targets.json"
DEFAULT_TARGET="mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"

[[ -f "$EXAMPLE" ]] || die "Example configuration not found: $EXAMPLE"
[[ -f "$TARGETS" ]] || die "Hardware target manifest not found: $TARGETS"

target_exists(){
  python3 - "$TARGETS" "$1" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id') == sys.argv[2]]
raise SystemExit(0 if len(items)==1 else 1)
PY
}

while true; do
  callsign="$(prompt_default 'Station callsign (without SSID)' 'N0CALL')"
  callsign="${callsign^^}"
  [[ "$callsign" =~ ^[A-Z0-9]{1,6}$ ]] && break
  warn "Callsign must be 1..6 alphanumeric characters."
done

while true; do
  ssid="$(prompt_default 'SSID' '0')"
  [[ "$ssid" =~ ^[0-9]+$ ]] && (( ssid >= 0 && ssid <= 15 )) && break
  warn "SSID must be 0..15."
done

section "Hardware target"
step "Initial qualified target: $DEFAULT_TARGET"
warn "YWD-1278 will only manipulate HAT BOOT/RESET GPIOs for the explicitly selected allowlisted target."
while true; do
  hardware_target="$(prompt_default 'Hardware target' "$DEFAULT_TARGET")"
  target_exists "$hardware_target" && break
  warn "Unknown hardware target. Choose an ID present in firmware/targets.json."
done

while true; do
  frequency="$(prompt_default 'Packet frequency MHz (0 disables radio configuration)' '0.0')"
  python3 - "$frequency" <<'PY' >/dev/null 2>&1 && break || true
import sys
f=float(sys.argv[1])
assert f == 0.0 or 100.0 <= f <= 1000.0
PY
  warn "Enter 0.0 or a numeric frequency between 100 and 1000 MHz. Band-plan/transmit validation is enforced separately."
done

device="$(prompt_default 'Modem UART' '/dev/ttyAMA0')"
kiss_port="$(prompt_default 'TCP KISS port' '8001')"
console_port="$(prompt_default 'TNC console/Telnet port' '8010')"

[[ "$kiss_port" =~ ^[0-9]+$ ]] && (( kiss_port >= 1 && kiss_port <= 65535 )) || die "Invalid KISS port"
[[ "$console_port" =~ ^[0-9]+$ ]] && (( console_port >= 1 && console_port <= 65535 )) || die "Invalid console port"
[[ "$kiss_port" != "$console_port" ]] || die "KISS and console ports must differ"

section "Configuration summary"
step "Station: ${callsign}-${ssid}"
step "Hardware: $hardware_target"
step "UART: $device"
step "Frequency: $frequency MHz"
step "KISS: 127.0.0.1:$kiss_port"
step "Console: 127.0.0.1:$console_port"
warn "RF transmit remains DISABLED after setup. Enabling TX is a later explicit configuration/qualification step."

confirm_exact "SAVE" "Write this configuration?" || die "Setup cancelled"

mkdir -p "$CONFIG_DIR"
chmod 0755 "$CONFIG_DIR"
if [[ -f "$CONFIG_FILE" ]]; then
  backup="$CONFIG_FILE.pre-setup.$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG_FILE" "$backup"
  chmod 0600 "$backup"
  info "Existing configuration backed up to $backup"
fi

cat >"$CONFIG_FILE" <<EOF
[station]
callsign = "$callsign"
ssid = $ssid

[hardware]
target = "$hardware_target"

[radio]
device = "$device"
frequency_mhz = $frequency
tx_power = 64
tx_enabled = false

[packet]
baud = 1200
txdelay_ms = 300
persist = 63
slottime_ms = 100
paclen = 128
maxframe = 4
retry = 10

[kiss]
enabled = true
listen = "127.0.0.1"
port = $kiss_port

[console]
enabled = true
listen = "127.0.0.1"
port = $console_port

[monitor]
enabled = true
log_frames = true

[storage]
database = "/var/lib/ywd-1278/ywd-1278.sqlite3"

[beacon]
enabled = false
interval_seconds = 600
destination = "BEACON"
path = []
text = "YWD-1278 packet node"

[firmware]
required_product = "YWD-1278"
allow_automatic_flash = false
EOF
chmod 0640 "$CONFIG_FILE"
ok "Configuration written: $CONFIG_FILE"
ok "RF transmit remains disabled"
