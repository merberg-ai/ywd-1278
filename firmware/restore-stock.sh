#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../installer/lib/ui.sh"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
HAT_CONTROL="$SCRIPT_DIR/hat_control.py"
DEVICE=/dev/ttyAMA0
BACKUP_DIR=""
ALLOW_UNRESPONSIVE=0
CONFIRM=""
BOOTLOADER_ACTIVE=0
STATE_FILE="$(mktemp /tmp/ywd1278-restore-services.XXXXXX)"

usage(){
  cat <<'EOF'
Usage:
  sudo ./firmware/restore-stock.sh --backup-dir DIR [--device /dev/ttyAMA0] \
    [--allow-unresponsive] --confirm RESTORE-STOCK

This recovery tool accepts only a verified target-bound stock backup. It uses
the qualified Raspberry Pi GPIO bootloader path, verifies the STM32 bootloader
identity, writes the stock main-flash image, reads all main flash back, verifies
the exact stock SHA256, restarts the application, and verifies its exact stock
GET_VERSION identity.

No option-byte write command is issued.
EOF
}

while (($#)); do
  case "$1" in
    --backup-dir) BACKUP_DIR="${2:?missing value}"; shift ;;
    --device) DEVICE="${2:?missing value}"; shift ;;
    --allow-unresponsive) ALLOW_UNRESPONSIVE=1 ;;
    --confirm) CONFIRM="${2:?missing value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || die "--backup-dir must name a protected YWD-1278 stock backup directory"
[[ "$CONFIRM" == RESTORE-STOCK ]] || die "Restore requires --confirm RESTORE-STOCK"
[[ -f "$TARGETS" && -f "$HAT_CONTROL" ]] || die "Firmware tooling is incomplete"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"
command_exists stm32flash || die "stm32flash is required"

META="$BACKUP_DIR/manifest.json"
IMAGE="$BACKUP_DIR/original-flash.bin"
[[ -f "$META" && -f "$IMAGE" ]] || die "Backup directory is incomplete"

target_id="$(python3 - "$META" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
print(m.get('target_id',''))
PY
)"
[[ -n "$target_id" ]] || die "Backup metadata has no target_id"

json_target(){
  local field="$1"
  python3 - "$TARGETS" "$target_id" "$field" <<'PY'
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

flash_base="$(json_target flash_base)" || die "Backup target is no longer allowlisted: $target_id"
flash_size="$(json_target flash_size_bytes)"
stock_sha="$(json_target stock_flash_sha256)"
boot_method="$(json_target bootloader_entry)"
boot_version="$(json_target expected_bootloader_version)"
device_id="$(json_target expected_device_id)"
option_bytes="$(json_target option_bytes_permitted)"
ywd_prefix="$(json_target ywd1278_identity_prefix)"

[[ "$boot_method" == pi-gpio20-21 ]] || die "Target does not have the qualified automatic bootloader path"
[[ "$option_bytes" == false ]] || die "Target policy permits option-byte writes; refusing restore"
[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size > 0 )) || die "Invalid target flash geometry"
[[ "$stock_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Target has no exact stock SHA256"

captured_identity="$(python3 - "$TARGETS" "$target_id" "$META" "$IMAGE" <<'PY'
import hashlib,json,sys
targets,target_id,meta_path,image_path=sys.argv[1:]
data=json.load(open(targets,encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1: raise SystemExit('target mismatch')
t=items[0]
m=json.load(open(meta_path,encoding='utf-8'))
identity=m.get('captured_identity')
if identity not in (t.get('stock_identities') or []): raise SystemExit('backup identity is not allowlisted stock')
if m.get('target_id') != target_id: raise SystemExit('backup target mismatch')
if m.get('flash_base') != t.get('flash_base'): raise SystemExit('backup flash base mismatch')
if int(m.get('flash_size_bytes',-1)) != int(t.get('flash_size_bytes',-2)): raise SystemExit('backup geometry mismatch')
if int(m.get('schema',0)) < 2: raise SystemExit('backup is older than qualified two-pass schema')
if m.get('read_passes') != 2 or m.get('two_pass_byte_identical') is not True: raise SystemExit('backup lacks two-pass qualification')
if m.get('stock_sha256_match') is not True: raise SystemExit('backup lacks stock SHA qualification')
if m.get('option_bytes_read_or_written') is not False: raise SystemExit('backup metadata indicates option-byte activity')
raw=open(image_path,'rb').read()
if len(raw) != int(t['flash_size_bytes']): raise SystemExit('backup size mismatch')
sha=hashlib.sha256(raw).hexdigest().lower()
if sha != str(m.get('sha256','')).lower(): raise SystemExit('backup checksum mismatch')
if sha != str(t.get('stock_flash_sha256','')).lower(): raise SystemExit('backup differs from exact target stock image')
print(identity)
PY
)" || die "Backup failed protected-stock verification"

section "Verified stock recovery image"
step "Target: $target_id"
step "Captured identity: $captured_identity"
step "Image: $IMAGE"
step "Flash range: $flash_base + $flash_size bytes"
step "SHA256: $stock_sha"
step "Option-byte writes: FORBIDDEN"
ok "Protected two-pass stock backup verified"

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

cleanup(){
  local rc="$1"
  trap - EXIT
  set +e
  if (( BOOTLOADER_ACTIVE == 1 )); then
    python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$target_id" >/dev/null 2>&1 || true
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
  die "UART still busy: $DEVICE"
fi

probe_identity(){
  python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --json
}

section "Current application identity"
if current_json="$(probe_identity 2>/dev/null)"; then
  current_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$current_json")"
  step "$current_identity"
  current_ok="$(python3 - "$TARGETS" "$target_id" "$current_identity" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding='utf-8'))
t=[x for x in data.get('targets',[]) if x.get('id')==sys.argv[2]]
if len(t)!=1: raise SystemExit(2)
x=t[0]; ident=sys.argv[3]
accepted=x.get('accepted_running_identities') or []
prefix=x.get('ywd1278_identity_prefix') or ''
print('yes' if ident in accepted or (prefix and ident.startswith(prefix)) else 'no')
PY
)"
  [[ "$current_ok" == yes ]] || die "Responsive application identity does not match the backup target"
else
  [[ $ALLOW_UNRESPONSIVE -eq 1 ]] || die "HAT application is unresponsive. Re-run with --allow-unresponsive only for intentional recovery."
  warn "Application did not answer; recovery is proceeding because --allow-unresponsive was explicitly supplied."
fi

section "Automatic STM32 system bootloader entry"
python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$target_id" || die "Failed to request bootloader state"
BOOTLOADER_ACTIVE=1
sleep 0.5
boot_info="$(stm32flash -b 115200 "$DEVICE" 2>&1)" || { printf '%s\n' "$boot_info" >&2; die "STM32 bootloader did not answer"; }
printf '%s\n' "$boot_info"
STM32FLASH_INFO="$boot_info" python3 - "$boot_version" "$device_id" <<'PY'
import os,re,sys
vexp,iexp=sys.argv[1:]; text=os.environ.get('STM32FLASH_INFO','')
def g(label):
    m=re.search(rf"{label}\s*:\s*(0x[0-9A-Fa-f]+)",text)
    return m.group(1).lower() if m else ''
v=g('Version'); i=g('Device ID')
if v != vexp.lower() or i != iexp.lower(): raise SystemExit(2)
print(f'STM32_BOOTLOADER_VERSION={v}')
print(f'STM32_DEVICE_ID={i}')
print('STM32_BOOTLOADER_IDENTITY=PASS')
PY
ok "Expected STM32 bootloader verified"

section "RESTORE EXACT STOCK MAIN FLASH"
warn "This will overwrite STM32 main flash with the checksum-verified stock backup."
confirm_exact "WRITE-STOCK-NOW" "Restore the verified stock image now?" || die "Restore cancelled"
stm32flash -b 115200 -w "$IMAGE" -v "$DEVICE"
ok "Stock image write/verify reported success"

section "Full stock readback verification"
readback="$(mktemp /tmp/ywd1278-stock-restore-readback.XXXXXX.bin)"
stm32flash -b 115200 -r "$readback" -S "$flash_base:$flash_size" "$DEVICE"
readback_sha="$(sha256sum "$readback" | awk '{print $1}')"
rm -f "$readback"
printf 'STOCK_RESTORE_READBACK_SHA256=%s\n' "$readback_sha"
[[ "${readback_sha,,}" == "${stock_sha,,}" ]] || die "Restored main flash differs from exact stock SHA256"
ok "Complete restored main flash matches exact stock SHA256"

python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$target_id" || die "Failed to restart restored application"
BOOTLOADER_ACTIVE=0
sleep 1.5

section "Post-restore exact identity verification"
post_json="$(probe_identity)" || die "Restored stock application did not answer GET_VERSION"
post_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$post_json")"
[[ "$post_identity" == "$captured_identity" ]] || die "Restored identity differs from captured exact stock identity: $post_identity"
ok "Exact stock identity restored: $post_identity"

echo "YWD1278_STOCK_RESTORE=PASS"
echo "STOCK_RESTORE_SHA256=$readback_sha"
echo "FINAL_IDENTITY=$post_identity"
echo "RF_CONFIGURED=NO"
echo "OPTION_BYTES_WRITTEN=NO"
