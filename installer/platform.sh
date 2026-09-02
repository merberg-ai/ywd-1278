#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
MODE="${1:-audit}"
BOOT_CONFIG=""
CMDLINE_FILE=""

find_boot_files(){
  if [[ -f /boot/firmware/config.txt ]]; then BOOT_CONFIG=/boot/firmware/config.txt
  elif [[ -f /boot/config.txt ]]; then BOOT_CONFIG=/boot/config.txt
  else die "Raspberry Pi boot config not found"; fi

  if [[ -f /boot/firmware/cmdline.txt ]]; then CMDLINE_FILE=/boot/firmware/cmdline.txt
  elif [[ -f /boot/cmdline.txt ]]; then CMDLINE_FILE=/boot/cmdline.txt
  else die "Raspberry Pi kernel cmdline file not found"; fi
}

serial_console_present(){ grep -Eq '(^|[[:space:]])console=(serial0|ttyAMA0),' "$CMDLINE_FILE"; }
uart_runtime_ready(){
  [[ -e /dev/ttyAMA0 ]] || return 1
  command_exists pinctrl || return 1
  grep -q 'TXD0' <<<"$(pinctrl get 14 2>/dev/null || true)" || return 1
  grep -q 'RXD0' <<<"$(pinctrl get 15 2>/dev/null || true)" || return 1
  return 0
}

emit_audit(){
  local ready=NO console=NO reboot=NO reasons=()
  uart_runtime_ready && ready=YES || { reboot=YES; reasons+=(uart-not-ready); }
  serial_console_present && { console=YES; reboot=YES; reasons+=(serial-console); }
  echo "BOOT_CONFIG=$BOOT_CONFIG"
  echo "CMDLINE_FILE=$CMDLINE_FILE"
  echo "RUNTIME_UART_READY=$ready"
  echo "SERIAL_CONSOLE_PRESENT=$console"
  echo "REBOOT_REQUIRED=$reboot"
  if ((${#reasons[@]})); then
    local joined; joined="$(IFS=,; echo "${reasons[*]}")"
    echo "REBOOT_REASONS=$joined"
  else
    echo "REBOOT_REASONS=none"
  fi
}

apply_changes(){
  local changed=0 stamp="$(date +%Y%m%d-%H%M%S)"
  if ! uart_runtime_ready; then
    cp -a "$BOOT_CONFIG" "$BOOT_CONFIG.ywd1278-backup.$stamp"
    if ! grep -Fq '# YWD-1278 managed UART' "$BOOT_CONFIG"; then
      cat >>"$BOOT_CONFIG" <<'EOF'

[all]
# YWD-1278 managed UART
enable_uart=1
EOF
    fi
    changed=1
    ok "Configured Raspberry Pi UART for YWD-1278"
  fi

  if serial_console_present; then
    cp -a "$CMDLINE_FILE" "$CMDLINE_FILE.ywd1278-backup.$stamp"
    python3 - "$CMDLINE_FILE" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1])
text=p.read_text(encoding='utf-8').strip()
parts=[x for x in text.split() if not re.match(r'^console=(serial0|ttyAMA0),', x)]
p.write_text(' '.join(parts)+'\n', encoding='utf-8')
PY
    changed=1
    ok "Removed modem UART from Linux serial-console ownership"
  fi

  systemctl disable --now serial-getty@ttyAMA0.service serial-getty@serial0.service >/dev/null 2>&1 || true
  echo "PLATFORM_CHANGED=$([[ $changed -eq 1 ]] && echo YES || echo NO)"
  echo "REBOOT_REQUIRED=$([[ $changed -eq 1 ]] && echo YES || echo NO)"
}

find_boot_files
case "$MODE" in
  audit) emit_audit ;;
  apply) apply_changes ;;
  *) die "Usage: sudo $0 [audit|apply]" ;;
esac
