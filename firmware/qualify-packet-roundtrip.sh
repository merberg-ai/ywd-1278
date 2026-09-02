#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../installer/lib/ui.sh"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
HAT_CONTROL="$SCRIPT_DIR/hat_control.py"
TARGET_ID=""
FIRMWARE=""
BACKUP_DIR=""
DEVICE=/dev/ttyAMA0
CONFIRM=""
BOOTLOADER_ACTIVE=0
PACKET_WRITTEN=0
STOCK_RESTORED=0
STOCK_IMAGE=""
CAPTURED_IDENTITY=""
STATE_FILE="$(mktemp /tmp/ywd1278-p11-services.XXXXXX)"

usage(){
  cat <<'EOF'
Usage:
  sudo ./firmware/qualify-packet-roundtrip.sh \
    --target TARGET \
    --firmware FILE \
    --stock-backup-dir DIR \
    [--device /dev/ttyAMA0] \
    --confirm QUALIFY-0B-P11

0B-P11 is a qualification-only packet-firmware write path. It requires:
  * normal product flash_enabled=false;
  * the historical 0B-P3 write gate to remain closed;
  * a target-specific packet_qualification_write gate for phase 0B-P11;
  * the exact deterministic 0B-P10 packet artifact SHA256 and size;
  * exact stock application at start;
  * a verified two-pass protected stock backup;
  * same-run restoration of that exact stock backup.

P11 does not configure RF, start YWD_RX, or expose a packet TX command. The
only application-layer transaction used is MMDVM GET_VERSION through the safe
identity probe. If an error occurs after packet firmware has been written, the
EXIT recovery path attempts to restore and fully verify the stock image.
Option-byte write commands are never issued.
EOF
}

while (($#)); do
  case "$1" in
    --target) TARGET_ID="${2:?missing --target value}"; shift ;;
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    --stock-backup-dir) BACKUP_DIR="${2:?missing --stock-backup-dir value}"; shift ;;
    --device) DEVICE="${2:?missing --device value}"; shift ;;
    --confirm) CONFIRM="${2:?missing --confirm value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -n "$TARGET_ID" ]] || die "--target is required"
[[ -n "$FIRMWARE" && -f "$FIRMWARE" ]] || die "--firmware must name an existing file"
[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || die "--stock-backup-dir must name a protected stock backup"
[[ "$CONFIRM" == QUALIFY-0B-P11 ]] || die "Packet qualification requires --confirm QUALIFY-0B-P11"
[[ -f "$TARGETS" && -f "$HAT_CONTROL" ]] || die "Firmware tooling is incomplete"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"
command_exists stm32flash || die "stm32flash is required"

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
q_phase="$(json_target packet_qualification_write.phase)"
q_enabled="$(json_target packet_qualification_write.enabled)"
q_stock_start="$(json_target packet_qualification_write.requires_exact_stock_start)"
q_backup="$(json_target packet_qualification_write.requires_verified_stock_backup)"
q_restore="$(json_target packet_qualification_write.requires_stock_restore_same_run)"
q_rf="$(json_target packet_qualification_write.rf_configuration_permitted)"
q_rx="$(json_target packet_qualification_write.rx_start_permitted)"
q_tx="$(json_target packet_qualification_write.tx_command_permitted)"
flash_base="$(json_target flash_base)"
flash_size="$(json_target flash_size_bytes)"
expected_sha="$(json_target packet_firmware_candidate.artifact_sha256)"
expected_size="$(json_target packet_firmware_candidate.artifact_size_bytes)"
expected_identity="$(json_target packet_firmware_candidate.expected_identity)"
candidate_status="$(json_target packet_firmware_candidate.status)"
candidate_repro="$(json_target packet_firmware_candidate.reproducibility)"
candidate_runtime_verified="$(json_target packet_firmware_candidate.runtime_identity_verified)"
candidate_accepted="$(json_target packet_firmware_candidate.accepted_running_identity)"
stock_sha="$(json_target stock_flash_sha256)"
boot_method="$(json_target bootloader_entry)"
boot_version="$(json_target expected_bootloader_version)"
device_id="$(json_target expected_device_id)"
option_bytes="$(json_target option_bytes_permitted)"

[[ "$flash_enabled" == false ]] || die "0B-P11 must not run with normal product flashing enabled"
[[ "$p3_enabled" == false ]] || die "Historical 0B-P3 qualification gate must remain closed during P11"
[[ "$q_phase" == 0B-P11 && "$q_enabled" == true ]] || die "Target does not expose the guarded 0B-P11 packet qualification gate"
[[ "$q_stock_start" == true && "$q_backup" == true && "$q_restore" == true ]] || die "0B-P11 stock safety requirements are incomplete"
[[ "$q_rf" == false && "$q_rx" == false && "$q_tx" == false ]] || die "0B-P11 packet gate permits an RF/RX/TX operation; refusing qualification"
[[ "$boot_method" == pi-gpio20-21 ]] || die "Target lacks the qualified GPIO bootloader method"
[[ "$option_bytes" == false ]] || die "Target policy permits option-byte writes; refusing qualification"
[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size == 131072 )) || die "Unexpected flash geometry: $flash_size"
[[ "$expected_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Packet candidate lacks an exact SHA256"
[[ "$expected_size" =~ ^[0-9]+$ ]] || die "Packet candidate lacks an exact artifact size"
[[ -n "$expected_identity" ]] || die "Packet candidate lacks an exact runtime identity"
[[ "$candidate_status" == deterministic-build-qualified-runtime-unqualified ]] || die "Packet candidate is not in the expected pre-P11 state"
[[ "$candidate_repro" == pass ]] || die "Packet candidate did not pass deterministic reproducibility"
[[ "$candidate_runtime_verified" == false && "$candidate_accepted" == false ]] || die "Packet candidate is already marked runtime-qualified/accepted; refusing stale P11 gate"

artifact_sha="$(sha256sum "$FIRMWARE" | awk '{print $1}')"
artifact_size="$(stat -c %s "$FIRMWARE")"
[[ "${artifact_sha,,}" == "${expected_sha,,}" ]] || die "Firmware does not match the exact 0B-P10 qualified packet SHA256"
[[ "$artifact_size" == "$expected_size" ]] || die "Firmware size does not match the exact 0B-P10 packet artifact size"
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

section "0B-P11 packet qualification gates"
step "Target: $TARGET_ID"
step "Packet firmware SHA256: $artifact_sha"
step "Packet firmware bytes: $artifact_size"
step "Expected packet identity: $expected_identity"
step "Stock backup: $BACKUP_DIR"
step "Stock SHA256: $stock_sha"
step "Normal product flash_enabled: $flash_enabled"
step "Historical P3 write gate: CLOSED"
step "P11 packet qualification gate: ENABLED"
step "RF configuration: FORBIDDEN"
step "RX start: FORBIDDEN"
step "TX command: FORBIDDEN"
step "Option-byte writes: FORBIDDEN"

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
  warn "0B-P11 failed after packet firmware was written; attempting automatic exact-stock recovery."
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$TARGET_ID" || return 1
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE" || return 1

  local recovery_readback recovery_sha j ident
  recovery_readback="$(mktemp /tmp/ywd1278-p11-emergency-stock.XXXXXX.bin)"
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
  restore_services
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
start_json="$(probe_identity)" || die "HAT application did not answer before P11"
start_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$start_json")"
step "$start_identity"
[[ "$start_identity" == "$CAPTURED_IDENTITY" ]] || die "0B-P11 must start from the exact stock identity captured by the verified backup"
ok "Exact stock start state verified"

warn "This qualification will write the exact build-qualified YWD-1278 AX25R3 packet image to STM32 main flash, verify it, perform GET_VERSION only, then restore the exact verified stock image in the same run."
confirm_exact "WRITE-PACKET-YWD-THEN-RESTORE-STOCK" "Proceed with the guarded 0B-P11 packet write/readback/identity/restore round trip?" || die "0B-P11 cancelled"

section "Write exact qualified packet firmware artifact"
enter_bootloader || die "Unable to enter the expected STM32 bootloader"
stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"
PACKET_WRITTEN=1
ok "Packet firmware artifact write/verify reported success"

section "Read back programmed packet firmware bytes"
packet_readback="$(mktemp /tmp/ywd1278-p11-packet-readback.XXXXXX.bin)"
stm32flash -b 115200 -r "$packet_readback" -S "$flash_base:$artifact_size" "$DEVICE"
packet_readback_sha="$(sha256sum "$packet_readback" | awk '{print $1}')"
rm -f "$packet_readback"
printf 'PACKET_READBACK_SHA256=%s\n' "$packet_readback_sha"
[[ "${packet_readback_sha,,}" == "${expected_sha,,}" ]] || die "Programmed packet bytes do not match the exact 0B-P10 artifact SHA256"
ok "Programmed packet bytes match the exact 0B-P10 artifact"

restart_application || die "Unable to restart packet firmware application"
section "Exact packet firmware identity gate — GET_VERSION only"
packet_json="$(probe_identity)" || die "Packet firmware image did not answer GET_VERSION"
packet_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$packet_json")"
step "$packet_identity"
[[ "$packet_identity" == "$expected_identity" ]] || die "Packet firmware identity differs from the exact 0B-P10 expected identity"
ok "Exact packet firmware GET_VERSION identity verified"

section "Restore exact protected stock image"
enter_bootloader || die "Unable to re-enter STM32 bootloader for stock restore"
stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"
ok "Stock image write/verify reported success"

section "Read back complete restored stock flash"
stock_readback="$(mktemp /tmp/ywd1278-p11-stock-readback.XXXXXX.bin)"
stm32flash -b 115200 -r "$stock_readback" -S "$flash_base:$flash_size" "$DEVICE"
stock_readback_sha="$(sha256sum "$stock_readback" | awk '{print $1}')"
rm -f "$stock_readback"
printf 'STOCK_RESTORE_READBACK_SHA256=%s\n' "$stock_readback_sha"
[[ "${stock_readback_sha,,}" == "${stock_sha,,}" ]] || die "Restored stock main flash does not match the exact P2 stock SHA256"
ok "Complete restored stock flash matches the exact P2 SHA256"

restart_application || die "Unable to restart restored stock application"
section "Final exact stock identity gate"
final_json="$(probe_identity)" || die "Restored stock application did not answer GET_VERSION"
final_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$final_json")"
step "$final_identity"
[[ "$final_identity" == "$CAPTURED_IDENTITY" ]] || die "Final stock identity does not match the protected backup identity"
STOCK_RESTORED=1
ok "Exact stock application identity restored"

echo "YWD1278_0B_P11_PACKET_ROUNDTRIP=PASS"
echo "PACKET_ARTIFACT_SHA256=$expected_sha"
echo "PACKET_READBACK_SHA256=$packet_readback_sha"
echo "PACKET_IDENTITY=$packet_identity"
echo "STOCK_BACKUP_SHA256=$stock_sha"
echo "STOCK_RESTORE_READBACK_SHA256=$stock_readback_sha"
echo "FINAL_IDENTITY=$final_identity"
echo "NORMAL_FLASH_ENABLED=NO"
echo "P3_QUALIFICATION_GATE=CLOSED"
echo "P11_PACKET_QUALIFICATION_GATE=ENABLED"
echo "APPLICATION_COMMANDS_SENT=GET_VERSION_ONLY"
echo "RF_CONFIGURED=NO"
echo "RX_STARTED=NO"
echo "RF_TRANSMITTED=NO"
echo "OPTION_BYTES_WRITTEN=NO"
