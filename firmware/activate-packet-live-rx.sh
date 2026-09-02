#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$ROOT/installer/lib/ui.sh"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
HAT_CONTROL="$SCRIPT_DIR/hat_control.py"
LIVE_RX_TOOL="$ROOT/tools/qualify_live_rx_owner.py"
TARGET_ID=""
FIRMWARE=""
BACKUP_DIR=""
DEVICE=/dev/ttyAMA0
CONFIRM=""
SECONDS=3
BOOTLOADER_ACTIVE=0
PACKET_WRITTEN=0
STOCK_RESTORED=0
SUCCESS=0
STOCK_IMAGE=""
CAPTURED_IDENTITY=""
STATE_FILE="$(mktemp /tmp/ywd1278-p12a-services.XXXXXX)"

usage(){
  cat <<'EOF'
Usage:
  sudo bash firmware/activate-packet-live-rx.sh \
    --target TARGET \
    --firmware FILE \
    --stock-backup-dir DIR \
    [--device /dev/ttyAMA0] \
    [--seconds 3] \
    --confirm QUALIFY-0B-P12A

0B-P12a is a guarded activation + receive-only lifecycle qualification. It:
  * requires normal product flash_enabled=false;
  * requires the historical P3 and P11 write gates to remain closed;
  * permits only the exact P10/P11-qualified packet artifact;
  * requires exact stock firmware at start and the exact P2 stock backup;
  * writes and reads back the exact packet artifact;
  * verifies the exact packet GET_VERSION identity;
  * runs the single-owner RX-only lifecycle at the manifest frequency;
  * automatically restores and fully verifies exact stock on any failure after
    the packet image is written;
  * intentionally leaves the packet firmware installed only after a complete
    P12a receive-only PASS.

P12a configures the receiver using normal MMDVM SET_FREQ + a fixed idle
SET_CONFIG, starts/stops YWD_RX, and drains its FIFO. It has no packet TX
command path. Option-byte write commands are never issued.
EOF
}

while (($#)); do
  case "$1" in
    --target) TARGET_ID="${2:?missing --target value}"; shift ;;
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    --stock-backup-dir) BACKUP_DIR="${2:?missing --stock-backup-dir value}"; shift ;;
    --device) DEVICE="${2:?missing --device value}"; shift ;;
    --seconds) SECONDS="${2:?missing --seconds value}"; shift ;;
    --confirm) CONFIRM="${2:?missing --confirm value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -n "$TARGET_ID" ]] || die "--target is required"
[[ -n "$FIRMWARE" && -f "$FIRMWARE" ]] || die "--firmware must name an existing file"
[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || die "--stock-backup-dir must name a protected stock backup"
[[ "$CONFIRM" == QUALIFY-0B-P12A ]] || die "Live-RX activation requires --confirm QUALIFY-0B-P12A"
[[ -f "$TARGETS" && -f "$HAT_CONTROL" && -f "$LIVE_RX_TOOL" ]] || die "P12a tooling is incomplete"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"
command_exists stm32flash || die "stm32flash is required"
python3 - "$SECONDS" <<'PY' || die "--seconds must be numeric in the range 1..15"
import sys
v=float(sys.argv[1])
assert 1.0 <= v <= 15.0
PY

json_target(){
  local field="$1"
  python3 - "$TARGETS" "$TARGET_ID" "$field" <<'PY'
import json,sys
path,target_id,field=sys.argv[1:]
data=json.load(open(path,encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1: raise SystemExit(3)
v=items[0]
for part in field.split('.'):
    if not isinstance(v,dict): v=None; break
    v=v.get(part)
if isinstance(v,bool): print('true' if v else 'false')
elif v is None: print('')
else: print(v)
PY
}

flash_enabled="$(json_target flash_enabled)" || die "Unknown target: $TARGET_ID"
p3_enabled="$(json_target qualification_write.enabled)"
p11_enabled="$(json_target packet_qualification_write.enabled)"
q_phase="$(json_target packet_live_rx_activation.phase)"
q_enabled="$(json_target packet_live_rx_activation.enabled)"
q_stock_start="$(json_target packet_live_rx_activation.requires_exact_stock_start)"
q_backup="$(json_target packet_live_rx_activation.requires_verified_stock_backup)"
q_recovery="$(json_target packet_live_rx_activation.requires_automatic_stock_recovery_on_failure)"
q_leave="$(json_target packet_live_rx_activation.leave_packet_firmware_installed_on_success)"
q_frequency="$(json_target packet_live_rx_activation.receive_frequency_hz)"
q_tx="$(json_target packet_live_rx_activation.tx_command_permitted)"
q_option="$(json_target packet_live_rx_activation.option_bytes_permitted)"
flash_base="$(json_target flash_base)"
flash_size="$(json_target flash_size_bytes)"
expected_sha="$(json_target packet_firmware_candidate.artifact_sha256)"
expected_size="$(json_target packet_firmware_candidate.artifact_size_bytes)"
expected_identity="$(json_target packet_firmware_candidate.expected_identity)"
candidate_status="$(json_target packet_firmware_candidate.status)"
candidate_runtime_verified="$(json_target packet_firmware_candidate.runtime_identity_verified)"
candidate_accepted="$(json_target packet_firmware_candidate.accepted_running_identity)"
stock_sha="$(json_target stock_flash_sha256)"
boot_method="$(json_target bootloader_entry)"
boot_version="$(json_target expected_bootloader_version)"
device_id="$(json_target expected_device_id)"
option_bytes="$(json_target option_bytes_permitted)"

[[ "$flash_enabled" == false ]] || die "P12a must not run with normal product flashing enabled"
[[ "$p3_enabled" == false && "$p11_enabled" == false ]] || die "Historical P3/P11 qualification write gates must remain closed during P12a"
[[ "$q_phase" == 0B-P12a && "$q_enabled" == true ]] || die "Target does not expose the guarded 0B-P12a live-RX activation gate"
[[ "$q_stock_start" == true && "$q_backup" == true && "$q_recovery" == true && "$q_leave" == true ]] || die "P12a activation/recovery requirements are incomplete"
[[ "$q_tx" == false && "$q_option" == false ]] || die "P12a policy permits TX or option-byte writes; refusing activation"
[[ "$boot_method" == pi-gpio20-21 ]] || die "Target lacks the qualified GPIO bootloader method"
[[ "$option_bytes" == false ]] || die "Target policy permits option-byte writes; refusing activation"
[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size == 131072 )) || die "Unexpected flash geometry: $flash_size"
[[ "$expected_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Packet candidate lacks an exact SHA256"
[[ "$expected_size" =~ ^[0-9]+$ ]] || die "Packet candidate lacks an exact artifact size"
[[ -n "$expected_identity" ]] || die "Packet candidate lacks an exact runtime identity"
[[ "$candidate_status" == deterministic-build-and-runtime-qualified ]] || die "Packet candidate is not P11 runtime-qualified"
[[ "$candidate_runtime_verified" == true && "$candidate_accepted" == true ]] || die "Packet candidate is not an accepted P11-qualified running identity"
[[ "$q_frequency" =~ ^[0-9]+$ ]] || die "P12a manifest receive frequency is invalid"

artifact_sha="$(sha256sum "$FIRMWARE" | awk '{print $1}')"
artifact_size="$(stat -c %s "$FIRMWARE")"
[[ "${artifact_sha,,}" == "${expected_sha,,}" ]] || die "Firmware does not match the exact P10/P11 qualified packet SHA256"
[[ "$artifact_size" == "$expected_size" ]] || die "Firmware size does not match the exact P10/P11 packet artifact size"
(( artifact_size > 0 && artifact_size <= flash_size )) || die "Packet firmware artifact size is invalid for target geometry"

STOCK_IMAGE="$BACKUP_DIR/original-flash.bin"
BACKUP_META="$BACKUP_DIR/manifest.json"
[[ -f "$STOCK_IMAGE" && -f "$BACKUP_META" ]] || die "Protected backup directory is incomplete"

CAPTURED_IDENTITY="$(python3 - "$TARGETS" "$TARGET_ID" "$BACKUP_META" "$STOCK_IMAGE" <<'PY'
import hashlib,json,sys
path,target_id,meta_path,image_path=sys.argv[1:]
data=json.load(open(path,encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1: raise SystemExit('target mismatch')
t=items[0]
meta=json.load(open(meta_path,encoding='utf-8'))
if int(meta.get('schema',0)) < 2: raise SystemExit('backup schema is not the qualified two-pass form')
identity=meta.get('captured_identity')
if identity not in (t.get('stock_identities') or []): raise SystemExit('backup identity is not allowlisted stock')
if meta.get('target_id') != target_id: raise SystemExit('backup target mismatch')
if meta.get('flash_base') != t.get('flash_base'): raise SystemExit('backup flash base mismatch')
if int(meta.get('flash_size_bytes',-1)) != int(t.get('flash_size_bytes',-2)): raise SystemExit('backup geometry mismatch')
if meta.get('read_passes') != 2 or meta.get('two_pass_byte_identical') is not True: raise SystemExit('backup lacks two-pass qualification')
if meta.get('stock_sha256_match') is not True: raise SystemExit('backup did not qualify against stock hash')
if meta.get('option_bytes_read_or_written') is not False: raise SystemExit('backup metadata indicates option-byte activity')
if meta.get('flash_written') is not False: raise SystemExit('backup capture unexpectedly recorded a flash write')
raw=open(image_path,'rb').read()
if len(raw) != int(t['flash_size_bytes']): raise SystemExit('stock image length mismatch')
sha=hashlib.sha256(raw).hexdigest().lower()
if sha != str(meta.get('sha256','')).lower(): raise SystemExit('backup manifest checksum mismatch')
if sha != str(t.get('stock_flash_sha256','')).lower(): raise SystemExit('backup does not match target stock SHA256')
print(identity)
PY
)" || die "Protected stock backup failed 0B-P2 verification"

section "0B-P12a activation/live-RX gates"
step "Target: $TARGET_ID"
step "Packet firmware SHA256: $artifact_sha"
step "Packet firmware bytes: $artifact_size"
step "Expected packet identity: $expected_identity"
step "RX frequency: $q_frequency Hz"
step "Live RX interval: $SECONDS s"
step "Stock backup: $BACKUP_DIR"
step "Stock SHA256: $stock_sha"
step "Normal product flash_enabled: $flash_enabled"
step "Historical P3 write gate: CLOSED"
step "Historical P11 write gate: CLOSED"
step "P12a live-RX activation gate: ENABLED"
step "RX configuration/start: PERMITTED"
step "Packet TX command: FORBIDDEN"
step "Option-byte writes: FORBIDDEN"
step "Success final firmware: PACKET IMAGE (intentional)"
step "Failure final firmware: EXACT STOCK RECOVERY REQUIRED"

known_units=(ywd-1278.service MMDVMHost.service mmdvmhost.service ywd-mmdvmhost.service ywd-hotspot-mmdvmhost.service)

restore_services(){
  local kind unit enabled active
  [[ -f "$STATE_FILE" ]] || return 0
  while IFS='|' read -r kind unit enabled active; do
    [[ "$kind" == UNIT ]] || continue
    case "$enabled" in
      enabled|enabled-runtime|linked|linked-runtime) systemctl enable "$unit" >/dev/null 2>&1 || true ;;
      disabled) systemctl disable "$unit" >/dev/null 2>&1 || true ;;
      masked|masked-runtime) systemctl mask "$unit" >/dev/null 2>&1 || true ;;
    esac
    [[ "$active" == active ]] && systemctl start "$unit" >/dev/null 2>&1 || true
  done <"$STATE_FILE"
  rm -f "$STATE_FILE"
}

probe_identity(){
  python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --no-application-release --json
}

validate_bootloader_info(){
  local text="$1"
  STM32FLASH_INFO="$text" python3 - "$boot_version" "$device_id" <<'PY'
import os,re,sys
expected_version,expected_id=sys.argv[1:]
text=os.environ.get('STM32FLASH_INFO','')
def grab(label):
    m=re.search(rf"{label}\s*:\s*(0x[0-9A-Fa-f]+)",text)
    return m.group(1).lower() if m else ''
version=grab('Version'); device=grab('Device ID')
if not version or not device: raise SystemExit(2)
if version != expected_version.lower() or device != expected_id.lower(): raise SystemExit(3)
print(f'STM32_BOOTLOADER_VERSION={version}')
print(f'STM32_DEVICE_ID={device}')
print('STM32_BOOTLOADER_IDENTITY=PASS')
PY
}

enter_bootloader(){
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  local info
  info="$(stm32flash -b 115200 "$DEVICE" 2>&1)" || { printf '%s\n' "$info" >&2; return 1; }
  printf '%s\n' "$info"
  validate_bootloader_info "$info"
}

restart_application(){
  python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=0
  sleep 1.5
}

emergency_stock_restore(){
  warn "P12a failed after packet firmware was written; attempting automatic exact-stock recovery."
  if fuser "$DEVICE" >/dev/null 2>&1; then
    fuser -v "$DEVICE" >&2 || true
    warn "UART still has an owner before emergency recovery."
    return 1
  fi
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE" || return 1

  local recovery_readback recovery_sha j ident
  recovery_readback="$(mktemp /tmp/ywd1278-p12a-emergency-stock.XXXXXX.bin)"
  stm32flash -b 115200 -r "$recovery_readback" -S "$flash_base:$flash_size" "$DEVICE" || { rm -f "$recovery_readback"; return 1; }
  recovery_sha="$(sha256sum "$recovery_readback" | awk '{print $1}')"
  rm -f "$recovery_readback"
  [[ "${recovery_sha,,}" == "${stock_sha,,}" ]] || return 1
  echo "EMERGENCY_STOCK_RESTORE_READBACK_SHA256=$recovery_sha"

  python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=0
  sleep 1.5
  j="$(probe_identity)" || return 1
  ident="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$j")"
  [[ "$ident" == "$CAPTURED_IDENTITY" ]] || return 1
  STOCK_RESTORED=1
  echo "EMERGENCY_STOCK_RESTORE=PASS"
}

cleanup(){
  local rc="$1"
  trap - EXIT
  set +e
  if (( rc != 0 && PACKET_WRITTEN == 1 && STOCK_RESTORED == 0 )); then
    emergency_stock_restore || echo "EMERGENCY_STOCK_RESTORE=FAIL" >&2
  elif (( BOOTLOADER_ACTIVE == 1 )); then
    python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" >/dev/null 2>&1 || true
  fi

  if (( SUCCESS == 1 )); then
    # P12b needs a known-free UART. Do not restart any prior modem owner after a
    # successful activation; leave recorded units stopped and report this fact.
    rm -f "$STATE_FILE"
  else
    restore_services
  fi
  exit "$rc"
}
trap 'cleanup $?' EXIT

: >"$STATE_FILE"
for unit in "${known_units[@]}"; do
  load="$(systemctl show -p LoadState --value "$unit" 2>/dev/null || true)"
  [[ -n "$load" && "$load" != not-found ]] || continue
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  printf 'UNIT|%s|%s|%s\n' "$unit" "$enabled" "$active" >>"$STATE_FILE"
  systemctl stop "$unit" >/dev/null 2>&1 || true
done
sleep 0.25
if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART still has an owner after stopping known services"
fi

section "Exact stock start gate"
start_json="$(probe_identity)" || die "HAT application did not answer before P12a"
start_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$start_json")"
step "$start_identity"
[[ "$start_identity" == "$CAPTURED_IDENTITY" ]] || die "P12a must start from the exact stock identity captured by the verified backup"
ok "Exact stock start state verified"

warn "P12a will write the exact P10/P11-qualified AX25R3 packet image, verify its readback/identity, configure receive-only operation at $q_frequency Hz, run a bounded YWD_RX lifecycle, then restart the packet firmware cold and LEAVE IT INSTALLED on success. Any failure after the write triggers exact-stock recovery."
confirm_exact "ACTIVATE-PACKET-RX-ONLY" "Proceed with guarded 0B-P12a packet activation and live receive-only lifecycle?" || die "P12a cancelled"

section "Write exact qualified packet firmware artifact"
enter_bootloader || die "Unable to enter the expected STM32 bootloader"
stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"
PACKET_WRITTEN=1
ok "Packet firmware artifact write/verify reported success"

section "Read back programmed packet firmware bytes"
packet_readback="$(mktemp /tmp/ywd1278-p12a-packet-readback.XXXXXX.bin)"
stm32flash -b 115200 -r "$packet_readback" -S "$flash_base:$artifact_size" "$DEVICE"
packet_readback_sha="$(sha256sum "$packet_readback" | awk '{print $1}')"
rm -f "$packet_readback"
printf 'PACKET_READBACK_SHA256=%s\n' "$packet_readback_sha"
[[ "${packet_readback_sha,,}" == "${expected_sha,,}" ]] || die "Programmed packet bytes do not match the exact P10/P11 artifact SHA256"
ok "Programmed packet bytes match the exact qualified packet artifact"

restart_application || die "Unable to restart packet firmware application"
section "Exact packet firmware identity gate"
packet_json="$(probe_identity)" || die "Packet firmware image did not answer GET_VERSION"
packet_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$packet_json")"
step "$packet_identity"
[[ "$packet_identity" == "$expected_identity" ]] || die "Packet firmware identity differs from the exact P11-qualified identity"
ok "Exact packet firmware identity verified"

section "Live single-owner YWD_RX lifecycle"
python3 "$LIVE_RX_TOOL" \
  --device "$DEVICE" \
  --identity "$expected_identity" \
  --frequency-hz "$q_frequency" \
  --seconds "$SECONDS"

if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART was not released after live RX owner qualification"
fi
ok "Live RX owner released the UART"

section "Restart qualified packet image cold"
restart_application || die "Unable to restart packet firmware after live RX qualification"
final_json="$(probe_identity)" || die "Packet firmware did not answer after final cold restart"
final_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$final_json")"
step "$final_identity"
[[ "$final_identity" == "$expected_identity" ]] || die "Final packet identity differs after cold restart"
if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART is unexpectedly owned after final packet identity probe"
fi

SUCCESS=1

echo "YWD1278_0B_P12A_PACKET_LIVE_RX=PASS"
echo "PACKET_ARTIFACT_SHA256=$expected_sha"
echo "PACKET_READBACK_SHA256=$packet_readback_sha"
echo "PACKET_IDENTITY=$final_identity"
echo "RX_FREQUENCY_HZ=$q_frequency"
echo "PACKET_FIRMWARE_LEFT_INSTALLED=YES"
echo "FINAL_PACKET_RESTARTED=YES"
echo "MODEM_UART_RELEASED=YES"
echo "KNOWN_MODEM_SERVICES_LEFT_STOPPED=YES"
echo "NORMAL_FLASH_ENABLED=NO"
echo "P3_QUALIFICATION_GATE=CLOSED"
echo "P11_PACKET_QUALIFICATION_GATE=CLOSED"
echo "P12A_LIVE_RX_ACTIVATION_GATE=ENABLED"
echo "RF_RECEIVE_CONFIGURED_DURING_TEST=YES"
echo "TX_COMMAND_PATH=ABSENT"
echo "RF_TRANSMITTED=NO"
echo "OPTION_BYTES_WRITTEN=NO"
