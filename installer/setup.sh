#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
banner

SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG_DIR=/etc/ywd-1278
CONFIG_FILE="$CONFIG_DIR/config.toml"
EXAMPLE="$SOURCE_ROOT/config/ywd-1278.example.toml"
DETECTED_TARGET="${YWD1278_DETECTED_TARGET:-}"
DETECTED_IDENTITY="${YWD1278_DETECTED_IDENTITY:-}"
FIRMWARE_CLASS="${YWD1278_FIRMWARE_CLASS:-}"
FIRMWARE_DESCRIPTION="${YWD1278_FIRMWARE_DESCRIPTION:-}"
[[ -f "$EXAMPLE" ]] || die "Example configuration not found: $EXAMPLE"

toml_get(){
  local section_name="$1" key="$2" fallback="$3"
  python3 - "$CONFIG_FILE" "$section_name" "$key" "$fallback" <<'PY'
import sys,tomllib
from pathlib import Path
p=Path(sys.argv[1]); section,key,fallback=sys.argv[2:]
if not p.exists(): print(fallback); raise SystemExit
try:
    with p.open('rb') as f: data=tomllib.load(f)
    value=data.get(section,{}).get(key,fallback)
except Exception:
    value=fallback
if isinstance(value,bool): print('true' if value else 'false')
else: print(value)
PY
}

old_callsign="$(toml_get station callsign N0CALL)"
old_ssid="$(toml_get station ssid 0)"
old_target="$(toml_get hardware target '')"
old_frequency="$(toml_get radio frequency_mhz 0.0)"
old_device="$(toml_get radio device /dev/ttyAMA0)"
old_kiss="$(toml_get kiss port 8001)"
old_console="$(toml_get console port 8010)"

parse_detection(){
  local out="$1"
  DETECTED_TARGET="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$out" | tail -1)"
  DETECTED_IDENTITY="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$out" | tail -1)"
  FIRMWARE_CLASS="$(sed -n 's/^FIRMWARE_CLASS=//p' <<<"$out" | tail -1)"
  FIRMWARE_DESCRIPTION="$(sed -n 's/^FIRMWARE_DESCRIPTION=//p' <<<"$out" | tail -1)"
}

try_setup_detect(){
  local allow="${1:-0}" out rc
  local -a args=(--device "$old_device")
  [[ "$allow" == 1 ]] && args+=(--allow-candidate-release)
  if out="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SCRIPT_DIR/hardware-detect.sh" "${args[@]}" 2>&1)"; then rc=0; else rc=$?; fi
  printf '%s\n' "$out"
  parse_detection "$out"
  return "$rc"
}

section "Hardware discovery"
if [[ -z "$DETECTED_IDENTITY" ]]; then
  if try_setup_detect 0; then
    detect_rc=0
  else
    detect_rc=$?
  fi

  if [[ $detect_rc -eq 20 ]]; then
    warn "The UART is available but the HAT did not answer. It may be a supported HAT held in reset by Raspberry Pi GPIO defaults."
    if confirm_yes_no "Try the qualified supported-HAT application-release GPIO profile?" yes; then
      try_setup_detect 1 || true
    fi
  elif [[ $detect_rc -eq 22 ]]; then
    warn "A modem answered GET_VERSION, but its firmware identity is not recognized by this YWD-1278 build."
  elif [[ $detect_rc -ne 0 ]]; then
    warn "No supported HAT was identified during setup. Configuration can still be saved safely."
  fi
else
  ok "Installer already identified the attached HAT; reusing that live detection result."
fi

if [[ -n "$DETECTED_TARGET" ]]; then
  ok "Hardware target: $DETECTED_TARGET"
fi
if [[ -n "$DETECTED_IDENTITY" ]]; then
  step "Firmware identity: $DETECTED_IDENTITY"
  step "Firmware class: ${FIRMWARE_CLASS:-UNKNOWN}"
  [[ -z "$FIRMWARE_DESCRIPTION" ]] || step "$FIRMWARE_DESCRIPTION"
  case "${FIRMWARE_CLASS:-UNKNOWN}" in
    STOCK) ok "Recognized stock firmware is currently installed on the HAT" ;;
    YWD1278) ok "Recognized YWD-1278 firmware is currently installed on the HAT" ;;
    YWD_ENGINEERING) warn "A recognized pre-product YWD engineering firmware is installed; it is not the final YWD-1278 product firmware" ;;
    KNOWN_OTHER) info "The HAT is running another explicitly allowlisted firmware identity" ;;
    UNKNOWN|AMBIGUOUS|*) warn "Firmware identity is not a uniquely supported YWD-1278 firmware state; no firmware action will be taken" ;;
  esac
fi

section "Station configuration"
while true; do
  callsign="$(prompt_default 'Station callsign (without SSID)' "$old_callsign")"
  callsign="${callsign^^}"
  [[ "$callsign" =~ ^[A-Z0-9]{1,6}$ ]] && break
  warn "Callsign must be 1..6 alphanumeric characters."
done

while true; do
  ssid="$(prompt_default 'SSID' "$old_ssid")"
  [[ "$ssid" =~ ^[0-9]+$ ]] && (( ssid >= 0 && ssid <= 15 )) && break
  warn "SSID must be 0..15."
done

hardware_target="$old_target"
if [[ -n "$DETECTED_TARGET" ]]; then
  hardware_target="$DETECTED_TARGET"
  ok "Using detected supported HAT target: $hardware_target"
elif [[ -n "$hardware_target" ]]; then
  info "Retaining previously configured HAT target: $hardware_target"
else
  warn "No supported HAT target is bound yet; hardware auto-detection will be retried later."
fi

while true; do
  frequency="$(prompt_default 'Packet frequency MHz (0 disables radio configuration)' "$old_frequency")"
  python3 - "$frequency" <<'PY' >/dev/null 2>&1 && break || true
import sys
f=float(sys.argv[1])
assert f == 0.0 or 100.0 <= f <= 1000.0
PY
  warn "Enter 0.0 or a numeric frequency between 100 and 1000 MHz."
done

device="$(prompt_default 'Modem UART' "$old_device")"
kiss_port="$(prompt_default 'TCP KISS port' "$old_kiss")"
console_port="$(prompt_default 'TNC console/Telnet port' "$old_console")"
[[ "$kiss_port" =~ ^[0-9]+$ ]] && (( kiss_port >= 1 && kiss_port <= 65535 )) || die "Invalid KISS port"
[[ "$console_port" =~ ^[0-9]+$ ]] && (( console_port >= 1 && console_port <= 65535 )) || die "Invalid console port"
[[ "$kiss_port" != "$console_port" ]] || die "KISS and console ports must differ"

section "Configuration summary"
step "Station: ${callsign}-${ssid}"
step "Hardware: ${hardware_target:-auto-detect pending}"
[[ -z "$DETECTED_IDENTITY" ]] || step "Current HAT firmware: ${FIRMWARE_CLASS:-UNKNOWN} — $DETECTED_IDENTITY"
step "UART: $device"
step "Frequency: $frequency MHz"
step "KISS: 127.0.0.1:$kiss_port"
step "Console: 127.0.0.1:$console_port"
step "Pseudo-serial TNC: /run/ywd-1278/tnc"
warn "RF transmit remains DISABLED after setup."

confirm_exact "SAVE" "Write this configuration?" || die "Setup cancelled"
mkdir -p "$CONFIG_DIR"; chmod 0755 "$CONFIG_DIR"
if [[ -f "$CONFIG_FILE" ]]; then
  backup="$CONFIG_FILE.pre-setup.$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG_FILE" "$backup"; chmod 0600 "$backup"
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
pty_enabled = true
pty_link = "/run/ywd-1278/tnc"

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
