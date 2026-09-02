#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UI="$SCRIPT_DIR/../installer/lib/ui.sh"
# shellcheck source=../installer/lib/ui.sh
source "$UI"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
HAT_CONTROL="$SCRIPT_DIR/hat_control.py"
DEVICE=/dev/ttyAMA0
TARGET_ID=""
FIRMWARE=""
STOCK_BACKUP_DIR=""
MODE="${1:-probe}"
[[ $# -gt 0 ]] && shift || true
CONFIRM=""
BACKUP_ROOT=/var/lib/ywd-1278/firmware-backups
BOOTLOADER_ACTIVE=0

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
  * backup performs two independent main-flash reads and never reads option bytes
  * known stock firmware must match its allowlisted full-flash SHA256
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
[[ -f "$HAT_CONTROL" ]] || die "HAT control helper missing: $HAT_CONTROL"
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
import hashlib,json,sys
targets,target_id,meta_path,image_path=sys.argv[1:]
data=json.load(open(targets, encoding='utf-8'))
t=[x for x in data.get('targets',[]) if x.get('id')==target_id]
if len(t)!=1: raise SystemExit(1)
target=t[0]
meta=json.load(open(meta_path, encoding='utf-8'))
if meta.get('target_id') != target_id: raise SystemExit(1)
if meta.get('captured_identity') not in (target.get('stock_identities') or []): raise SystemExit(1)
if meta.get('option_bytes_read_or_written') not in (False, None): raise SystemExit(1)
if meta.get('read_passes') != 2 or meta.get('two_pass_byte_identical') is not True: raise SystemExit(1)
raw=open(image_path,'rb').read()
if len(raw) != int(meta.get('flash_size_bytes',-1)): raise SystemExit(1)
if len(raw) != int(target.get('flash_size_bytes',-2)): raise SystemExit(1)
sha=hashlib.sha256(raw).hexdigest().lower()
if sha != str(meta.get('sha256','')).lower(): raise SystemExit(1)
stock_sha=str(target.get('stock_flash_sha256') or '').lower()
if stock_sha and sha != stock_sha: raise SystemExit(1)
if meta.get('stock_sha256_match') is not True: raise SystemExit(1)
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

restart_application_quiet(){
  [[ $BOOTLOADER_ACTIVE -eq 1 && -n "$TARGET_ID" ]] || return 0
  python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" >/dev/null 2>&1 || true
  BOOTLOADER_ACTIVE=0
  sleep 0.5
}

cleanup(){
  restart_application_quiet
  restore_services
}
trap cleanup EXIT

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
  section "Safe HAT identity probe"
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
bootloader_method="$(json_target bootloader_entry)"
expected_boot_version="$(json_target expected_bootloader_version)"
expected_device_id="$(json_target expected_device_id)"
stock_flash_sha="$(json_target stock_flash_sha256)"

section "Target"
step "$TARGET_ID"
step "$description"
step "manifest status: $status"
[[ "$option_bytes" == false ]] || die "Target manifest permits option-byte writes; YWD-1278 policy forbids this"
[[ "$bootloader_method" == pi-gpio20-21 ]] || die "Target bootloader entry is not qualified for automatic YWD-1278 control"

stop_known_owners
section "Application identity gate"
probe_json="$(probe_identity)" || die "Unable to identify running HAT application; refusing bootloader operation"
identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$probe_json")"
step "Running identity: $identity"
match_identity "$identity" || die "Running identity does not match requested target; refusing operation"
ok "Running identity matches allowlisted target"

[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size > 0 )) || die "Target flash geometry is not qualified for read testing yet (flash_size_bytes=$flash_size)"
command_exists stm32flash || die "stm32flash is required"

validate_bootloader_info(){
  local text="$1"
  python3 - "$expected_boot_version" "$expected_device_id" <<'PY' <<<"$text"
import re,sys
expected_version,expected_id=sys.argv[1:]
text=sys.stdin.read()
def grab(label):
    m=re.search(rf"{label}\s*:\s*(0x[0-9A-Fa-f]+)", text)
    return m.group(1).lower() if m else ''
version=grab('Version')
device=grab('Device ID')
if not version or not device:
    print('STM32_BOOTLOADER_PARSE=FAIL', file=sys.stderr)
    raise SystemExit(2)
print(f'STM32_BOOTLOADER_VERSION={version}')
print(f'STM32_DEVICE_ID={device}')
if expected_version and version != expected_version.lower():
    print(f'expected bootloader {expected_version}, got {version}', file=sys.stderr)
    raise SystemExit(3)
if expected_id and device != expected_id.lower():
    print(f'expected device {expected_id}, got {device}', file=sys.stderr)
    raise SystemExit(4)
print('STM32_BOOTLOADER_IDENTITY=PASS')
PY
}

enter_bootloader(){
  section "Enter STM32 system bootloader"
  python3 "$HAT_CONTROL" bootloader-entry --targets "$TARGETS" --target "$TARGET_ID" || die "Failed to request target bootloader state"
  BOOTLOADER_ACTIVE=1
  sleep 0.5
  local info
  info="$(stm32flash -b 115200 "$DEVICE" 2>&1)" || {
    printf '%s\n' "$info" >&2
    die "STM32 bootloader did not answer"
  }
  printf '%s\n' "$info"
  validate_bootloader_info "$info" || die "STM32 bootloader identity did not match target"
  ok "STM32 bootloader responded with the expected identity"
}

restart_application(){
  section "Return HAT to application"
  python3 "$HAT_CONTROL" application-restart --targets "$TARGETS" --target "$TARGET_ID" || die "Failed to restart target application"
  BOOTLOADER_ACTIVE=0
  sleep 1.5
}

make_backup(){
  local stamp dir read_a read_b image sha_a sha_b size_a size_b stock_match=false
  stamp="$(date +%Y%m%d-%H%M%S)"
  dir="$BACKUP_ROOT/$TARGET_ID/$stamp"
  read_a="$dir/read-a.bin"
  read_b="$dir/read-b.bin"
  image="$dir/original-flash.bin"
  install -d -m 0700 "$dir"

  enter_bootloader
  section "Protected two-pass main-flash backup"
  step "Read range: $flash_base + $flash_size bytes"
  step "Option-byte region: NOT READ"

  stm32flash -b 115200 -r "$read_a" -S "$flash_base:$flash_size" "$DEVICE"
  chmod 0600 "$read_a"
  stm32flash -b 115200 -r "$read_b" -S "$flash_base:$flash_size" "$DEVICE"
  chmod 0600 "$read_b"

  size_a="$(stat -c %s "$read_a")"
  size_b="$(stat -c %s "$read_b")"
  [[ "$size_a" == "$flash_size" && "$size_b" == "$flash_size" ]] || die "Backup read size mismatch: A=$size_a B=$size_b expected=$flash_size"

  sha_a="$(sha256sum "$read_a" | awk '{print $1}')"
  sha_b="$(sha256sum "$read_b" | awk '{print $1}')"
  printf 'BACKUP_READ_A_SHA256=%s\n' "$sha_a"
  printf 'BACKUP_READ_B_SHA256=%s\n' "$sha_b"
  cmp -s "$read_a" "$read_b" || die "Independent main-flash reads are not byte-identical"
  [[ "$sha_a" == "$sha_b" ]] || die "Independent main-flash read SHA256 values differ"
  ok "Two independent $flash_size-byte reads are byte-identical"

  if identity_is_stock "$identity"; then
    [[ "$stock_flash_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Target has no allowlisted stock main-flash SHA256"
    [[ "${sha_a,,}" == "${stock_flash_sha,,}" ]] || die "Stock flash SHA256 differs from the qualified golden baseline"
    stock_match=true
    ok "Stock main-flash SHA256 matches the qualified golden baseline"
  fi

  install -m 0600 "$read_a" "$image"
  rm -f "$read_a" "$read_b"

  python3 - "$dir/manifest.json" "$TARGET_ID" "$identity" "$DEVICE" "$flash_base" "$flash_size" "$sha_a" "$stock_flash_sha" "$stock_match" "$expected_boot_version" "$expected_device_id" <<'PY'
import json,sys,time
(path,target,identity,device,base,size,sha,stock_sha,stock_match,boot_version,device_id)=sys.argv[1:]
obj={
  "schema":2,
  "target_id":target,
  "captured_identity":identity,
  "device":device,
  "flash_base":base,
  "flash_size_bytes":int(size),
  "sha256":sha,
  "read_passes":2,
  "two_pass_byte_identical":True,
  "stock_sha256_expected":stock_sha or None,
  "stock_sha256_match":stock_match.lower()=="true",
  "expected_bootloader_version":boot_version or None,
  "expected_device_id":device_id or None,
  "captured_unix":int(time.time()),
  "option_bytes_read_or_written":False,
  "flash_written":False
}
open(path,'w',encoding='utf-8').write(json.dumps(obj,indent=2,sort_keys=True)+'\n')
PY
  chmod 0600 "$dir/manifest.json"

  restart_application
  section "Post-backup application verification"
  post_json="$(probe_identity)" || die "Main flash was read successfully but the application did not return"
  post_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$post_json")"
  [[ "$post_identity" == "$identity" ]] || die "Application identity changed across backup operation: $post_identity"
  ok "Application returned with the exact pre-backup identity"

  ok "Protected backup verified: $image"
  echo "BACKUP_DIR=$dir"
  echo "BACKUP_SHA256=$sha_a"
  echo "BACKUP_READ_PASSES=2"
  echo "BACKUP_TWO_PASS_IDENTICAL=YES"
  echo "GEOMETRY_VERIFIED_BYTES=$flash_size"
  echo "OPTION_BYTES_READ=NO"
  LAST_BACKUP_DIR="$dir"
}

if [[ "$MODE" == backup ]]; then
  make_backup
  if identity_is_stock "$identity"; then
    echo "BACKUP_CLASS=STOCK"
    echo "STOCK_SHA256_MATCH=YES"
  else
    echo "BACKUP_CLASS=NON_STOCK"
  fi
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

section "Firmware write gates"
[[ "$flash_enabled" == true ]] || die "Target is recognized but flash_enabled=false. No YWD-1278 firmware write is enabled for this target yet."
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

# This write path is unreachable while flash_enabled=false. No option-byte
# commands are present. Promotion requires a separately qualified checkpoint.
stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"
ok "Programmer reported write/verify success"
restart_application

section "Post-flash identity verification"
post="$(probe_identity)" || die "Firmware was written but application identity could not be verified. Use restore-stock.sh with the protected stock backup before further experimentation."
post_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$post")"
prefix="$(json_target ywd1278_identity_prefix)"
[[ -n "$prefix" && "$post_identity" == "$prefix"* ]] || die "Unexpected post-flash identity: $post_identity"
ok "Post-flash identity: $post_identity"
echo "YWD1278_FLASH=PASS"
echo "OPTION_BYTES_WRITTEN=NO"
