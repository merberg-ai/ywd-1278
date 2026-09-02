#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$ROOT/installer/lib/ui.sh"

require_root
banner

STAGE="$SCRIPT_DIR/qualification/0c-p2-rssi-live-stage.json"
TARGETS="$SCRIPT_DIR/targets.json"
HAT_CONTROL="$SCRIPT_DIR/hat_control.py"
PROBE="$SCRIPT_DIR/probe_hat.py"
LIVE_RSSI_TOOL="$ROOT/tools/qualify_live_rssi.py"
BACKUP_DIR=""
CONFIRM=""
BOOTLOADER_ACTIVE=0
CANDIDATE_WRITE_ATTEMPTED=0
BASE_RESTORED=0
STOCK_RESTORED=0
CAPTURED_STOCK_IDENTITY=""

usage(){
  cat <<'EOF'
Usage:
  sudo bash firmware/activate-rssi-live.sh \
    --stock-backup-dir DIR \
    --confirm QUALIFY-0C-P2-RSSI-RX-ONLY

0C-P2 guarded AX25R4 live RSSI activation.

The target, UART, frequency, exact AX25R3 base artifact, exact AX25R4
candidate, observation duration, poll interval, and confirmation token are
frozen in firmware/qualification/0c-p2-rssi-live-stage.json.

The run starts only from the exact P13b-qualified AX25R3 physical base, proves
its programmed prefix SHA256 before any write, installs only the locked AX25R4
candidate, verifies programmed bytes and GET_VERSION identity, then runs one
bounded receive-only raw-RSSI observation through the base ModemOwner.

If any step fails after the candidate write is attempted, the EXIT recovery
path first restores the exact P13b-qualified AX25R3 artifact and verifies its
readback and identity. If that rollback itself fails, the protected two-pass
stock backup is used as a final fallback recovery.

No YWD TX command is reachable from the live RSSI tool. KISS/product TX remains
disconnected. No carrier threshold or hysteresis is selected. STM32 option
bytes are never read or written.
EOF
}

while (($#)); do
  case "$1" in
    --stock-backup-dir) BACKUP_DIR="${2:?missing --stock-backup-dir value}"; shift ;;
    --confirm) CONFIRM="${2:?missing --confirm value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -f "$STAGE" && -f "$TARGETS" && -f "$HAT_CONTROL" && -f "$PROBE" && -f "$LIVE_RSSI_TOOL" ]] || die "0C-P2 live RSSI tooling is incomplete"
[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || die "--stock-backup-dir must name the protected two-pass stock backup"
command_exists stm32flash || die "stm32flash is required"

stage_get(){
  python3 - "$STAGE" "$1" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
for p in sys.argv[2].split('.'):
    if not isinstance(v,dict): v=None; break
    v=v.get(p)
if isinstance(v,bool): print('true' if v else 'false')
elif v is None: print('')
else: print(v)
PY
}

target_get(){
  local target_id="$1" field="$2"
  python3 - "$TARGETS" "$target_id" "$field" <<'PY'
import json,sys
path,target_id,field=sys.argv[1:]
data=json.load(open(path,encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1: raise SystemExit(3)
v=items[0]
for p in field.split('.'):
    if not isinstance(v,dict): v=None; break
    v=v.get(p)
if isinstance(v,bool): print('true' if v else 'false')
elif v is None: print('')
else: print(v)
PY
}

[[ "$(stage_get schema)" == 1 ]] || die "Unexpected P2 stage schema"
[[ "$(stage_get phase)" == 0C-P2 && "$(stage_get stage)" == live-rssi-activation ]] || die "Unexpected P2 stage manifest"
[[ "$(stage_get status)" == staged ]] || die "P2 live RSSI stage is not staged"

TARGET_ID="$(stage_get target_id)"
DEVICE="$(stage_get activation.device)"
FREQUENCY_HZ="$(stage_get activation.frequency_hz)"
DURATION_SECONDS="$(stage_get activation.duration_seconds)"
POLL_INTERVAL="$(stage_get activation.rssi_poll_interval_seconds)"
TOKEN="$(stage_get activation.confirmation_token)"
BASE_STATUS="$(stage_get physical_base.status)"
BASE_REL="$(stage_get physical_base.artifact)"
BASE_SIZE="$(stage_get physical_base.artifact_size_bytes)"
BASE_SHA="$(stage_get physical_base.artifact_sha256)"
BASE_IDENTITY="$(stage_get physical_base.identity)"
CANDIDATE_REL="$(stage_get candidate.artifact)"
CANDIDATE_SIZE="$(stage_get candidate.artifact_size_bytes)"
CANDIDATE_SHA="$(stage_get candidate.artifact_sha256)"
CANDIDATE_IDENTITY="$(stage_get candidate.identity)"

[[ "$CONFIRM" == "$TOKEN" ]] || die "Live RSSI activation requires --confirm $TOKEN"
[[ "$DEVICE" == /dev/ttyAMA0 ]] || die "P2 stage UART is not the frozen /dev/ttyAMA0"
[[ "$FREQUENCY_HZ" == 145050000 ]] || die "P2 stage frequency is not frozen 145.050 MHz"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"
[[ "$(stage_get activation.requires_exact_physical_base)" == true ]] || die "P2 stage does not require exact physical base"
[[ "$(stage_get activation.requires_verified_stock_backup)" == true ]] || die "P2 stage does not require protected stock recovery"
[[ "$(stage_get activation.automatic_base_restore_on_failure)" == true ]] || die "P2 stage lacks automatic AX25R3 rollback"
[[ "$(stage_get activation.fallback_stock_restore_on_base_restore_failure)" == true ]] || die "P2 stage lacks fallback stock recovery"
[[ "$(stage_get activation.leave_candidate_installed_on_success)" == true ]] || die "P2 stage success policy is unexpected"
[[ "$(stage_get safety.normal_product_flash_enabled)" == false ]] || die "P2 stage cannot run with product flashing enabled"
[[ "$(stage_get safety.qualification_write_only)" == true ]] || die "P2 stage is not qualification-write-only"
[[ "$(stage_get safety.tx_command_permitted)" == false ]] || die "P2 stage permits TX"
[[ "$(stage_get safety.kiss_tx_connected)" == false ]] || die "P2 stage connects KISS TX"
[[ "$(stage_get safety.product_tx_enabled)" == false ]] || die "P2 stage enables product TX"
[[ "$(stage_get safety.automatic_tx_retry)" == false ]] || die "P2 stage permits automatic TX retry"
[[ "$(stage_get safety.option_bytes_permitted)" == false ]] || die "P2 stage permits option-byte access"
[[ "$(stage_get safety.carrier_threshold_selected)" == false ]] || die "P2 stage prematurely selects a carrier threshold"
[[ "$(stage_get safety.hysteresis_selected)" == false ]] || die "P2 stage prematurely selects hysteresis"

flash_enabled="$(target_get "$TARGET_ID" flash_enabled)" || die "Unknown target: $TARGET_ID"
target_status="$(target_get "$TARGET_ID" status)"
option_bytes="$(target_get "$TARGET_ID" option_bytes_permitted)"
flash_base="$(target_get "$TARGET_ID" flash_base)"
flash_size="$(target_get "$TARGET_ID" flash_size_bytes)"
stock_sha="$(target_get "$TARGET_ID" stock_flash_sha256)"
boot_method="$(target_get "$TARGET_ID" bootloader_entry)"
boot_version="$(target_get "$TARGET_ID" expected_bootloader_version)"
device_id="$(target_get "$TARGET_ID" expected_device_id)"

[[ "$flash_enabled" == false ]] || die "Normal product flash_enabled must remain false"
[[ "$target_status" == "$BASE_STATUS" ]] || die "Current target status no longer matches frozen P13b physical base"
[[ "$option_bytes" == false ]] || die "Target permits option-byte access"
[[ "$boot_method" == pi-gpio20-21 ]] || die "Target lacks qualified GPIO bootloader entry"
[[ "$flash_size" == 131072 ]] || die "Unexpected flash geometry: $flash_size"

BASE="$ROOT/$BASE_REL"
CANDIDATE="$ROOT/$CANDIDATE_REL"
[[ -f "$BASE" ]] || die "Exact AX25R3 rollback artifact is missing: $BASE"
[[ -f "$CANDIDATE" ]] || die "Exact AX25R4 candidate is missing: $CANDIDATE"

verify_file(){
  local path="$1" expected_size="$2" expected_sha="$3" label="$4"
  local size sha
  size="$(stat -c %s "$path")"
  sha="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$size" == "$expected_size" ]] || die "$label size mismatch: expected=$expected_size actual=$size"
  [[ "${sha,,}" == "${expected_sha,,}" ]] || die "$label SHA256 mismatch: expected=$expected_sha actual=$sha"
}
verify_file "$BASE" "$BASE_SIZE" "$BASE_SHA" "AX25R3 base artifact"
verify_file "$CANDIDATE" "$CANDIDATE_SIZE" "$CANDIDATE_SHA" "AX25R4 candidate"
(( BASE_SIZE > 0 && BASE_SIZE <= flash_size )) || die "AX25R3 base size is invalid"
(( CANDIDATE_SIZE > 0 && CANDIDATE_SIZE <= flash_size )) || die "AX25R4 candidate size is invalid"

STOCK_IMAGE="$BACKUP_DIR/original-flash.bin"
BACKUP_META="$BACKUP_DIR/manifest.json"
[[ -f "$STOCK_IMAGE" && -f "$BACKUP_META" ]] || die "Protected stock backup directory is incomplete"
CAPTURED_STOCK_IDENTITY="$(python3 - "$TARGETS" "$TARGET_ID" "$BACKUP_META" "$STOCK_IMAGE" <<'PY'
import hashlib,json,sys
path,target_id,meta_path,image_path=sys.argv[1:]
data=json.load(open(path,encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1: raise SystemExit('target mismatch')
t=items[0]
meta=json.load(open(meta_path,encoding='utf-8'))
if int(meta.get('schema',0)) < 2: raise SystemExit('backup schema is not qualified two-pass form')
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
)" || die "Protected stock backup failed P2 verification"

known_units=(ywd-1278.service MMDVMHost.service mmdvmhost.service ywd-mmdvmhost.service ywd-hotspot-mmdvmhost.service)
for unit in "${known_units[@]}"; do
  [[ "$(systemctl is-active "$unit" 2>/dev/null || true)" != active ]] || die "Competing modem service is active: $unit (stop it before P2)"
done
if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART already has an owner before P2"
fi

probe_identity(){
  python3 "$PROBE" --device "$DEVICE" --targets "$TARGETS" --no-application-release --json
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

readback_prefix_sha(){
  local bytes="$1" tag="$2" tmp sha
  tmp="$(mktemp "/tmp/ywd1278-${tag}.XXXXXX.bin")"
  stm32flash -b 115200 -r "$tmp" -S "$flash_base:$bytes" "$DEVICE" || { rm -f "$tmp"; return 1; }
  sha="$(sha256sum "$tmp" | awk '{print $1}')"
  rm -f "$tmp"
  printf '%s' "$sha"
}

restore_base(){
  warn "Restoring exact P13b-qualified AX25R3 physical base."
  if fuser "$DEVICE" >/dev/null 2>&1; then
    fuser -v "$DEVICE" >&2 || true
    return 1
  fi
  enter_bootloader || return 1
  stm32flash -b 115200 -w "$BASE" -v "$DEVICE" || return 1
  local sha j ident
  sha="$(readback_prefix_sha "$BASE_SIZE" p2-base-rollback)" || return 1
  [[ "${sha,,}" == "${BASE_SHA,,}" ]] || return 1
  echo "BASE_ROLLBACK_READBACK_SHA256=$sha"
  restart_application || return 1
  j="$(probe_identity)" || return 1
  ident="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$j")"
  [[ "$ident" == "$BASE_IDENTITY" ]] || return 1
  BASE_RESTORED=1
  echo "AX25R3_BASE_RESTORE=PASS"
}

restore_stock(){
  warn "AX25R3 rollback failed; attempting final exact-stock recovery."
  if fuser "$DEVICE" >/dev/null 2>&1; then
    fuser -v "$DEVICE" >&2 || true
    return 1
  fi
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE" || return 1
  local tmp sha j ident
  tmp="$(mktemp /tmp/ywd1278-p2-stock-rollback.XXXXXX.bin)"
  stm32flash -b 115200 -r "$tmp" -S "$flash_base:$flash_size" "$DEVICE" || { rm -f "$tmp"; return 1; }
  sha="$(sha256sum "$tmp" | awk '{print $1}')"
  rm -f "$tmp"
  [[ "${sha,,}" == "${stock_sha,,}" ]] || return 1
  echo "STOCK_ROLLBACK_READBACK_SHA256=$sha"
  restart_application || return 1
  j="$(probe_identity)" || return 1
  ident="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$j")"
  [[ "$ident" == "$CAPTURED_STOCK_IDENTITY" ]] || return 1
  STOCK_RESTORED=1
  echo "FALLBACK_STOCK_RESTORE=PASS"
}

cleanup(){
  local rc="$1"
  trap - EXIT
  set +e
  if (( rc != 0 && CANDIDATE_WRITE_ATTEMPTED == 1 && BASE_RESTORED == 0 && STOCK_RESTORED == 0 )); then
    restore_base || restore_stock || echo "P2_AUTOMATIC_RECOVERY=FAIL" >&2
  elif (( BOOTLOADER_ACTIVE == 1 )); then
    python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap 'cleanup $?' EXIT

section "0C-P2 exact artifact/live RSSI gates"
step "Target: $TARGET_ID"
step "Physical base: $BASE_STATUS"
step "AX25R3 base SHA256: $BASE_SHA"
step "AX25R4 candidate SHA256: $CANDIDATE_SHA"
step "AX25R4 candidate bytes: $CANDIDATE_SIZE"
step "AX25R4 identity: $CANDIDATE_IDENTITY"
step "RX frequency: $FREQUENCY_HZ Hz"
step "Observation: $DURATION_SECONDS s at $POLL_INTERVAL s RSSI polling"
step "Normal flash_enabled: false"
step "TX command: FORBIDDEN"
step "KISS/product TX: DISCONNECTED"
step "Carrier threshold: NOT SELECTED"
step "Option-byte access: FORBIDDEN"
step "Failure rollback: exact AX25R3 first, exact stock fallback"

section "Exact P13b AX25R3 start gate"
start_json="$(probe_identity)" || die "HAT application did not answer before P2"
start_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$start_json")"
step "$start_identity"
[[ "$start_identity" == "$BASE_IDENTITY" ]] || die "P2 must start from the exact P13b-qualified AX25R3 identity"

enter_bootloader || die "Unable to enter expected STM32 bootloader for base readback"
base_readback_sha="$(readback_prefix_sha "$BASE_SIZE" p2-base-preflight)" || die "Unable to read current AX25R3 programmed prefix"
echo "BASE_PREFLIGHT_READBACK_SHA256=$base_readback_sha"
[[ "${base_readback_sha,,}" == "${BASE_SHA,,}" ]] || die "Current programmed AX25R3 bytes do not match the exact P13b physical base"
restart_application || die "Unable to restart AX25R3 after preflight readback"
base_json="$(probe_identity)" || die "AX25R3 did not answer after preflight restart"
base_identity_again="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$base_json")"
[[ "$base_identity_again" == "$BASE_IDENTITY" ]] || die "AX25R3 identity changed after preflight readback"
ok "Exact P13b AX25R3 programmed base verified"

warn "This will replace the currently qualified AX25R3 image with the exact staged AX25R4 RSSI candidate. The test is receive-only, but it DOES write STM32 main flash. On any failure after write is attempted, exact AX25R3 rollback is automatic, with exact stock as fallback."
confirm_exact "ACTIVATE-RSSI-RX-ONLY" "Proceed with guarded 0C-P2 AX25R4 activation?" || die "P2 cancelled"

section "Write exact locked AX25R4 candidate"
enter_bootloader || die "Unable to enter expected STM32 bootloader"
CANDIDATE_WRITE_ATTEMPTED=1
stm32flash -b 115200 -w "$CANDIDATE" -v "$DEVICE"
ok "AX25R4 write/verify reported success"

candidate_readback_sha="$(readback_prefix_sha "$CANDIDATE_SIZE" p2-candidate-readback)" || die "Unable to read back AX25R4 candidate bytes"
echo "CANDIDATE_READBACK_SHA256=$candidate_readback_sha"
[[ "${candidate_readback_sha,,}" == "${CANDIDATE_SHA,,}" ]] || die "Programmed AX25R4 bytes differ from locked candidate"
ok "Exact AX25R4 programmed readback verified"

restart_application || die "Unable to restart AX25R4 candidate"
candidate_json="$(probe_identity)" || die "AX25R4 candidate did not answer GET_VERSION"
candidate_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$candidate_json")"
[[ "$candidate_identity" == "$CANDIDATE_IDENTITY" ]] || die "AX25R4 runtime identity mismatch"
ok "Exact AX25R4 runtime identity verified"

section "Bounded receive-only raw RSSI observation"
python3 "$LIVE_RSSI_TOOL" \
  --device "$DEVICE" \
  --identity "$CANDIDATE_IDENTITY" \
  --frequency-hz "$FREQUENCY_HZ" \
  --seconds "$DURATION_SECONDS" \
  --poll-interval "$POLL_INTERVAL"

if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART was not released by live RSSI owner"
fi
ok "Single owner released UART"

section "Cold restart AX25R4 after receive-only proof"
restart_application || die "Unable to cold-restart AX25R4 after RSSI observation"
final_json="$(probe_identity)" || die "AX25R4 did not answer after final restart"
final_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$final_json")"
[[ "$final_identity" == "$CANDIDATE_IDENTITY" ]] || die "Final AX25R4 identity mismatch"
if fuser "$DEVICE" >/dev/null 2>&1; then
  fuser -v "$DEVICE" >&2 || true
  die "UART unexpectedly owned after final AX25R4 identity probe"
fi

trap - EXIT

echo "YWD1278_0C_P2_AX25R4_LIVE_RSSI_ACTIVATION=PASS"
echo "PHYSICAL_BASE_STATUS=$BASE_STATUS"
echo "BASE_PREFLIGHT_READBACK_SHA256=$base_readback_sha"
echo "CANDIDATE_ARTIFACT_SHA256=$CANDIDATE_SHA"
echo "CANDIDATE_READBACK_SHA256=$candidate_readback_sha"
echo "CANDIDATE_IDENTITY=$final_identity"
echo "RX_FREQUENCY_HZ=$FREQUENCY_HZ"
echo "AX25R4_LEFT_INSTALLED=YES"
echo "MODEM_UART_RELEASED=YES"
echo "NORMAL_FLASH_ENABLED=NO"
echo "KISS_TX_CONNECTED=NO"
echo "PRODUCT_TX_ENABLED=NO"
echo "TX_COMMAND_PATH=ABSENT_IN_LIVE_PROBE"
echo "CARRIER_THRESHOLD_SELECTED=NO"
echo "HYSTERESIS_SELECTED=NO"
echo "RF_TRANSMITTED=NO"
echo "OPTION_BYTES_WRITTEN=NO"
