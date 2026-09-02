#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../installer/lib/ui.sh
source "$SCRIPT_DIR/../installer/lib/ui.sh"

require_root
banner

TARGETS="$SCRIPT_DIR/targets.json"
DEVICE=/dev/ttyAMA0
BACKUP_DIR=""
ALLOW_UNRESPONSIVE=0
CONFIRM=""

usage(){
  cat <<'EOF'
Usage:
  sudo ./firmware/restore-stock.sh --backup-dir DIR [--device /dev/ttyAMA0] \
    --confirm RESTORE-STOCK

Options:
  --allow-unresponsive   Permit recovery when the application no longer answers
                         GET_VERSION. The protected backup metadata still must
                         identify an allowlisted target and a known stock identity.

This tool restores only backups whose captured identity is explicitly listed as
stock firmware for the target. It never writes option bytes.
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

[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || die "--backup-dir must name a protected YWD-1278 backup directory"
[[ "$CONFIRM" == RESTORE-STOCK ]] || die "Restore requires --confirm RESTORE-STOCK"
[[ -f "$BACKUP_DIR/manifest.json" && -f "$BACKUP_DIR/original-flash.bin" ]] || die "Backup directory is incomplete"
[[ -f "$TARGETS" ]] || die "Target manifest missing"
[[ -e "$DEVICE" ]] || die "UART does not exist: $DEVICE"
command_exists stm32flash || die "stm32flash is required"

read_meta(){
  python3 - "$BACKUP_DIR/manifest.json" "$1" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1], encoding='utf-8'))
v=obj.get(sys.argv[2])
print('' if v is None else v)
PY
}

target_id="$(read_meta target_id)"
captured_identity="$(read_meta captured_identity)"
flash_base="$(read_meta flash_base)"
flash_size="$(read_meta flash_size_bytes)"
expected_sha="$(read_meta sha256)"
option_meta="$(read_meta option_bytes_read_or_written)"
image="$BACKUP_DIR/original-flash.bin"

[[ "$option_meta" == False || "$option_meta" == false ]] || die "Backup metadata indicates option-byte activity; refusing restore"
[[ "$flash_size" =~ ^[0-9]+$ ]] && (( flash_size > 0 )) || die "Invalid backup flash size"
[[ "$expected_sha" =~ ^[0-9a-fA-F]{64}$ ]] || die "Invalid backup SHA256"
actual_sha="$(sha256sum "$image" | awk '{print $1}')"
[[ "${actual_sha,,}" == "${expected_sha,,}" ]] || die "Backup checksum mismatch"
[[ "$(stat -c %s "$image")" == "$flash_size" ]] || die "Backup size does not match metadata"

stock_match="$(python3 - "$TARGETS" "$target_id" "$captured_identity" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], encoding='utf-8'))
t=[x for x in data.get('targets',[]) if x.get('id')==sys.argv[2]]
if len(t)!=1: raise SystemExit(3)
print('yes' if sys.argv[3] in (t[0].get('stock_identities') or []) else 'no')
PY
)" || die "Backup target is no longer allowlisted: $target_id"
[[ "$stock_match" == yes ]] || die "Backup was not captured from an allowlisted stock identity: $captured_identity"

section "Verified stock backup"
step "Target: $target_id"
step "Captured identity: $captured_identity"
step "Image: $image"
step "SHA256: $actual_sha"
step "Flash range: $flash_base + $flash_size bytes"
ok "Backup metadata/checksum/stock identity verified"

known_units=(ywd-1278.service MMDVMHost.service mmdvmhost.service ywd-mmdvmhost.service ywd-hotspot-mmdvmhost.service)
STATE_FILE="$(mktemp /tmp/ywd1278-restore-services.XXXXXX)"
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
trap restore_services EXIT

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
  fail "UART still busy: $DEVICE"
  fuser -v "$DEVICE" >&2 || true
  exit 4
fi

section "Current application identity"
if current_json="$(python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --json 2>/dev/null)"; then
  current_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$current_json")"
  step "$current_identity"
else
  [[ $ALLOW_UNRESPONSIVE -eq 1 ]] || die "HAT application is unresponsive. Re-run with --allow-unresponsive only for intentional bootloader recovery."
  warn "Application did not answer; proceeding only because --allow-unresponsive was supplied."
  current_identity="<unresponsive>"
fi

section "Enter STM32 system bootloader"
step "Hold BOOT, tap/release RST, then release BOOT."
confirm_exact "BOOTLOADER-READY" "Place the exact HAT associated with this verified backup into its system bootloader." || die "Restore cancelled"
stm32flash -b 115200 "$DEVICE" >/tmp/ywd1278-stock-probe.$$ 2>&1 || {
  cat /tmp/ywd1278-stock-probe.$$ >&2 || true
  rm -f /tmp/ywd1278-stock-probe.$$
  die "STM32 bootloader did not answer"
}
rm -f /tmp/ywd1278-stock-probe.$$
ok "Bootloader responded"

section "RESTORE STOCK FIRMWARE"
warn "This writes the protected backup captured from: $captured_identity"
confirm_exact "WRITE-STOCK-NOW" "Write and verify the stock backup now?" || die "Restore cancelled"

# No option-byte commands are issued. The write source is the checksum-verified
# local backup captured from this allowlisted target.
stm32flash -b 115200 -w "$image" -v -g 0x0 "$DEVICE"
ok "Programmer reported stock image write/verify success"

sleep 1
section "Post-restore verification"
post_json="$(python3 "$SCRIPT_DIR/probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --json)" || die "Stock image was written but GET_VERSION verification failed"
post_identity="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["identity"])' <<<"$post_json")"
[[ "$post_identity" == "$captured_identity" ]] || die "Restored identity differs from captured stock identity: $post_identity"
ok "Stock identity restored exactly: $post_identity"
echo "YWD1278_STOCK_RESTORE=PASS"
echo "OPTION_BYTES_WRITTEN=NO"
