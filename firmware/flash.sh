#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UI="$SCRIPT_DIR/../installer/lib/ui.sh"
# shellcheck source=../installer/lib/ui.sh
source "$UI"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
DEVICE=/dev/ttyAMA0
TARGET_ID=""
FIRMWARE=""
STOCK_BACKUP_DIR=""
MODE="${1:-probe}"
[[ $# -gt 0 ]] && shift || true
CONFIRM=""
BACKUP_ROOT=/var/lib/ywd-1278/firmware-backups

usage(){
  cat <<'EOF'
YWD-1278 firmware tool

Usage:
  sudo ./firmware/flash.sh probe [--device /dev/ttyAMA0]
  sudo ./firmware/flash.sh backup --target TARGET [--device DEVICE]
  sudo ./firmware/flash.sh flash --target TARGET --firmware FILE [--device DEVICE] \
    [--stock-backup-dir DIR] --confirm FLASH-YWD-1278

Safety model:
  * only allowlisted targets are accepted
  * actual write requires target flash_enabled=true
  * target must specify nonzero flash geometry and an expected firmware SHA256
  * running application identity must match the target before bootloader entry
  * when stock rollback is required, a true stock backup is mandatory
  * an engineering/YWD firmware dump never satisfies the stock-backup gate
  * option-byte operations are never issued
  * unknown hardware fails closed
EOF
}

while (($#)); do
  case "$1" in
    --device) DEVICE="${2:?missing --device value}"; shift ;;
    --target) TARGET_ID="${2:?missing --target value}"; shift ;;
    --firmware) FIRMWARE="${2:?missing --firmware value}"; shift ;;
    --stock-backup-dir) STOCK_BACKUP_DIR="${2:?missing --stock-backup-dir value}"; shift ;;
    --confirm) CONFIRM="${2:?missing --confirm value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -f "$TARGETS" ]] || die "Target manifest missing: $TARGETS"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"

json_target(){
  local field="$1"
  python3 - "$TARGETS" "$TARGET_ID" "$field" <<'PY'
import json,sys
manifest,target_id,field=sys.argv[1:]
data=json.load(open(manifest, encoding='utf-8'))
items=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(items)!=1:
    raise SystemExit(3)
value=items[0].get(field)
if isinstance(value,bool): print('true' if value else 'false')
elif value is None: print('')
else: print(value)
PY
}

match_identity(){
  local identity="$1"
  python3 - "$TARGETS" "$TARGET_ID" "$identity" <<'PY'
import json,sys
manifest,target_id,identity=sys.argv[1:]
data=json.load(open(manifest, encoding='utf-8'))
t=[x for x in data['targets'] if x.get('id')==target_id]
assert len(t)==1
x=t[0]
exact=x.get('accepted_running_identities') or []
prefix=x.get('ywd1278_identity_prefix') or ''
raise SystemExit(0 if identity in exact or (prefix and identity.startswith(prefix)) else 1)
PY
}

identity_is_stock(){
  local identity="$1"
  python3 - "$TARGETS" "$TARGET_ID" "$identity" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], encoding='utf-8'))
t=[x for x in data.get('targets',[]) if x.get('id')==sys.argv[2]]
assert len(t)==1
raise SystemExit(0 if sys.argv[3] in (t[0].get('stock_identities') or []) else 1)
PY
}

verify_stock_backup_dir(){
  local dir="$1"
  [[ -d "$dir" && -f "$dir/manifest.json" && -f "$dir/original-flash.bin" ]] || return 1
  python3 - "$TARGETS" "$TARGET_ID" "$dir/manifest.json" "$dir/original-flash.bin" <<'PY'
import hashlib,json,os,sys
targets,target_id,meta_path,image_path=sys.argv[1:]
data=json.load(open(targets, encoding='utf-8'))
t=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(t)!=1: raise SystemExit(1)
meta=json.load(open(meta_path, encoding='utf-8'))
if meta.get('target_id') != target_id: raise SystemExit(1)
if meta.get('captured_identity') not in (t[0].get('stock_identities') or []): raise SystemExit(1)
if meta.get('option_bytes_read_or_written') not in (False, None): raise SystemExit(1)
raw=open(image_path,'rb').read()
if len(raw) != int(meta.get('flash_size_bytes',-1)): raise SystemExit(1)
if hashlib.sha256(raw).hexdigest().lower() != str(meta.get('sha256','')).lower(): raise SystemExit(1)
PY
}

known_units=(
  ywd-1278.service MMDVMHost.service mmdvmhost.service
  ywd-mmdvmhost.service ywd-hotspot-mmdvmhost.service
)
STATE_FILE="$(mktemp /tmp/ywd1278-flash-services.XXXXXX)"
restore_services(){
  local line unit active enabled
  [[ -f "$STATE_FILE" ]] || return 0
  while IFS='|' read -r line unit enabled active; do
    [[ "$line" == UNIT ]] || continue
    case "$enabled" in
      enabled|enabled-runtime|linked|linked-runtime) systemctl enable "$unit" >/dev/null 2>&1 || true ;;
      disabled) systemctl disable "$unit" >/dev/null 2>&1 || true ;;
      masked|masked-runtime) systemctl mask "$unit" >/dev/null 2>&1 || true ;;
    esac
    [[ "$active" == active ]] && systemctl start "$unit" >/dev/null 2>&1 || true
  done <"$STATE_FILE"
  rm -f "$STATE_FILE"
}
trap restore_services EXIT

stop_known_owners(){
  : >"$STATE_FILE"
  local unit load enabled active
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
    fail "UART still has an owner after stopping known services: $DEVICE"
    fuser -v "$DEVICE" >&2 || true
    exit 4
  fi
}

probe_identity(){
  python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --json
}

if [[ "$MODE" == probe ]]; then
  section "Read-only HAT probe"
  stop_known_owners
  python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS"
  ok "Probe completed without RF configuration or flash writes"
  exit 0
fi

[[ "$MODE" == backup || "$MODE" == flash ]] || { usage; die "Unknown mode: $MODE"; }
[[ -n "$TARGET_ID" ]] || die "--target is required for $MODE"

description="$(json_target description)" || die "Unknown target: $TARGET_ID"
status="$(json_target status)"
flash_enabled="$(json_target flash_enabled)"
flash_size="$(json_target flash_size_bytes)"
flash_base="$(json_target flash_base)"
backup_required="$(json_target stock_backup_required)"
option_bytes="$(json_target option_bytes_permitted)"

section "Target"
step "$TARGET_ID"
step "$description"
step "manifest status: $status"
[[ "$option_bytes" == false ]] || die "Target manifest permits option-byte writes; YWD-1278 policy forbids this"

stop_known_owners
section "Application identity gate"
probe_json="$(probe_identity)" || die "Unable to identify running HAT application; refusing bootloader operation"
identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$probe_json")"
step "Running identity: $identity"
match_identity "$identity" || die "Running identity does not match requested target; refusing operation"
ok "Running identity matches allowlisted target"

[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size > 0 )) || die "Target flash geometry is not qualified yet (flash_size_bytes=$flash_size)"
command_exists stm32flash || die "stm32flash is required"

enter_bootloader(){
  section "Enter STM32 system bootloader"
  warn "This target currently uses a manual BOOT/RST entry method."
  step "Hold the HAT BOOT button."
  step "Tap/release RST while continuing to hold BOOT briefly."
  step "Release BOOT."
  confirm_exact "BOOTLOADER-READY" "Do this only for the exact allowlisted HAT above." || die "Bootloader entry cancelled"
  stm32flash -b 115200 "$DEVICE" >/tmp/ywd1278-stm32-probe.$$ 2>&1 || {
    cat /tmp/ywd1278-stm32-probe.$$ >&2 || true
    rm -f /tmp/ywd1278-stm32-probe.$$
    die "STM32 bootloader did not answer"
  }
  rm -f /tmp/ywd1278-stm32-probe.$$
  ok "STM32 bootloader responded"
}

make_backup(){
  local stamp dir image sha size
  stamp="$(date +%Y%m%d-%H%M%S)"
  dir="$BACKUP_ROOT/$TARGET_ID/$stamp"
  image="$dir/original-flash.bin"
  install -d -m 0700 "$dir"
  enter_bootloader
  section "Protected flash backup"
  step "Reading $flash_size bytes from $flash_base"
  stm32flash -b 115200 -r "$image" -S "$flash_base:$flash_size" "$DEVICE"
  chmod 0600 "$image"
  size="$(stat -c %s "$image")"
  [[ "$size" == "$flash_size" ]] || die "Backup size mismatch: got $size expected $flash_size"
  sha="$(sha256sum "$image" | awk '{print $1}')"
  python3 - "$dir/manifest.json" "$TARGET_ID" "$identity" "$DEVICE" "$flash_base" "$flash_size" "$sha" <<'PY'
import json,sys,time
path,target,identity,device,base,size,sha=sys.argv[1:]
obj={"schema":1,"target_id":target,"captured_identity":identity,"device":device,
     "flash_base":base,"flash_size_bytes":int(size),"sha256":sha,
     "captured_unix":int(time.time()),"option_bytes_read_or_written":False}
open(path,'w',encoding='utf-8').write(json.dumps(obj,indent=2,sort_keys=True)+'\n')
PY
  chmod 0600 "$dir/manifest.json"
  ok "Backup verified: $image"
  echo "BACKUP_DIR=$dir"
  LAST_BACKUP_DIR="$dir"
}

if [[ "$MODE" == backup ]]; then
  make_backup
  if identity_is_stock "$identity"; then
    echo "BACKUP_CLASS=STOCK"
  else
    echo "BACKUP_CLASS=NON_STOCK"
  fi
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

section "Firmware write gates"
[[ "$flash_enabled" == true ]] || die "Target is recognized but flash_enabled=false. No YWD-1278 firmware is qualified for this target yet."
[[ -n "$FIRMWARE" && -f "$FIRMWARE" ]] || die "--firmware must name an existing file"
[[ "$CONFIRM" == FLASH-YWD-1278 ]] || die "Actual write requires --confirm FLASH-YWD-1278"
expected_sha="$(json_target firmware_sha256)"
[[ "$expected_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Target has no qualified firmware SHA256"
actual_sha="$(sha256sum "$FIRMWARE" | awk '{print $1}')"
[[ "${actual_sha,,}" == "${expected_sha,,}" ]] || die "Firmware SHA256 does not match allowlisted artifact"

if [[ "$backup_required" == true ]]; then
  section "Stock rollback gate"
  if identity_is_stock "$identity"; then
    info "Current firmware is an allowlisted stock identity; capturing a protected stock backup now."
    make_backup
    verify_stock_backup_dir "$LAST_BACKUP_DIR" || die "New stock backup did not pass rollback verification"
    ok "Fresh stock rollback backup verified"
  else
    [[ -n "$STOCK_BACKUP_DIR" ]] || die "Current firmware is not stock. Supply --stock-backup-dir with a previously captured verified stock backup before product flash."
    verify_stock_backup_dir "$STOCK_BACKUP_DIR" || die "Supplied stock backup is invalid, mismatched, non-stock, or corrupt"
    ok "Existing target-bound stock rollback backup verified: $STOCK_BACKUP_DIR"
  fi
fi

enter_bootloader
section "WRITE YWD-1278 firmware"
warn "Power loss during this step may require bootloader recovery."
confirm_exact "WRITE-FIRMWARE-NOW" "Last chance: write the verified image to the allowlisted HAT?" || die "Flash cancelled"

# Intentionally no stm32flash option-byte flags are used here. This command is
# unreachable until the target manifest is promoted to flash_enabled=true with
# qualified geometry and image hash.
stm32flash -b 115200 -w "$FIRMWARE" -v -g 0x0 "$DEVICE"
ok "Programmer reported write/verify success"

sleep 1
section "Post-flash identity verification"
post="$(probe_identity)" || die "Firmware was written but application identity could not be verified. Use restore-stock.sh with the protected stock backup before further experimentation."
post_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$post")"
prefix="$(json_target ywd1278_identity_prefix)"
[[ -n "$prefix" && "$post_identity" == "$prefix"* ]] || die "Unexpected post-flash identity: $post_identity"
ok "Post-flash identity: $post_identity"
echo "YWD1278_FLASH=PASS"
echo "OPTION_BYTES_WRITTEN=NO"
