#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
banner

PURGE_CONFIG=0
PURGE_STATE=0
PURGE_BACKUPS=0

usage(){
  cat <<'EOF'
Usage: sudo ./installer/uninstall.sh [options]

Options:
  --purge-config     Remove /etc/ywd-1278 after backup warning
  --purge-state      Remove non-firmware runtime state/logs
  --purge-backups    Also delete protected firmware backups (requires exact confirmation)
  -h, --help         Show help

Uninstall never flashes firmware. Use firmware/restore-stock.sh separately when
an intentional firmware restoration is desired.
EOF
}

while (($#)); do
  case "$1" in
    --purge-config) PURGE_CONFIG=1 ;;
    --purge-state) PURGE_STATE=1 ;;
    --purge-backups) PURGE_BACKUPS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

section "Stop service"
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/ywd-1278.service
systemctl daemon-reload
systemctl reset-failed ywd-1278.service >/dev/null 2>&1 || true
ok "Service removed"

section "Remove installed application"
rm -f /usr/local/bin/ywd1278
rm -rf /opt/ywd-1278
ok "Application files removed"

if [[ $PURGE_CONFIG -eq 1 ]]; then
  section "Purge configuration"
  [[ ! -d /etc/ywd-1278 ]] || confirm_exact "PURGE-CONFIG" "Delete /etc/ywd-1278?" || die "Configuration purge cancelled"
  rm -rf /etc/ywd-1278
  ok "Configuration removed"
else
  info "Configuration preserved: /etc/ywd-1278"
fi

if [[ $PURGE_STATE -eq 1 ]]; then
  section "Purge runtime state"
  if [[ -d /var/lib/ywd-1278 ]]; then
    # Keep firmware backups unless separately and explicitly authorized.
    find /var/lib/ywd-1278 -mindepth 1 -maxdepth 1 ! -name firmware-backups -exec rm -rf -- {} +
  fi
  rm -rf /var/log/ywd-1278
  ok "Non-firmware state removed"
else
  info "Runtime state/logs preserved"
fi

if [[ $PURGE_BACKUPS -eq 1 ]]; then
  section "DANGER: purge stock firmware backups"
  warn "These backups may be the only local path back to the HAT's original firmware."
  confirm_exact "DELETE-FIRMWARE-BACKUPS" "Permanently delete protected firmware backups?" || die "Backup purge cancelled"
  rm -rf /var/lib/ywd-1278/firmware-backups
  ok "Firmware backups deleted by explicit request"
else
  info "Protected firmware backups preserved: /var/lib/ywd-1278/firmware-backups"
fi

section "Uninstall complete"
ok "YWD-1278 host software removed"
warn "HAT firmware was NOT changed."
info "If YWD-1278 firmware is installed and stock restoration is desired, use the preserved restore tool/source checkout intentionally."
