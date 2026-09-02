#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
STATE_FILE=/var/lib/ywd-1278/install-resume.env
CONFIG=/etc/ywd-1278/config.toml
VENV=/opt/ywd-1278/venv
AUTOMATIC=0
[[ "${1:-}" == --automatic ]] && AUTOMATIC=1

[[ -f "$STATE_FILE" ]] || { info "No interrupted YWD-1278 installation needs resuming."; exit 0; }
# Root-created state contains only simple installer-owned assignments.
# shellcheck disable=SC1090
source "$STATE_FILE"
DEVICE="${DEVICE:-/dev/ttyAMA0}"
ALLOW_CANDIDATE_RELEASE="${ALLOW_CANDIDATE_RELEASE:-0}"

banner
section "Resume after reboot"
info "Continuing the installation from its saved checkpoint."

audit="$(bash "$SCRIPT_DIR/platform.sh" audit)"
printf '%s\n' "$audit"
grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" || die "UART is still not ready after reboot; installation state has been preserved"
grep -q '^SERIAL_CONSOLE_PRESENT=NO$' <<<"$audit" || die "Serial console still owns the modem UART; installation state has been preserved"

section "Supported HAT detection"
args=(--device "$DEVICE")
[[ "$ALLOW_CANDIDATE_RELEASE" == 1 ]] && args+=(--allow-candidate-release)
set +e
detect="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SCRIPT_DIR/hardware-detect.sh" "${args[@]}" 2>&1)"
rc=$?
set -e
printf '%s\n' "$detect"
[[ $rc -eq 0 ]] || die "HAT detection did not complete after reboot (rc=$rc); run sudo $SCRIPT_DIR/resume.sh after checking the HAT"
target="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$detect" | tail -1)"
[[ -n "$target" ]] || die "HAT detection returned no target"

python3 - "$CONFIG" "$target" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); target=sys.argv[2]
text=p.read_text(encoding='utf-8') if p.exists() else ''
if re.search(r'(?m)^\[hardware\]\s*$', text):
    block=re.compile(r'(?ms)(^\[hardware\]\s*$.*?)(?=^\[|\Z)')
    def repl(m):
        b=m.group(1)
        if re.search(r'(?m)^target\s*=', b):
            return re.sub(r'(?m)^target\s*=.*$', f'target = "{target}"', b)
        return b.rstrip()+f'\ntarget = "{target}"\n\n'
    text=block.sub(repl,text,count=1)
else:
    text=text.rstrip()+f'\n\n[hardware]\ntarget = "{target}"\n'
p.write_text(text,encoding='utf-8')
PY
chmod 0640 "$CONFIG"
ok "Configuration bound to detected HAT target: $target"

section "Final framework verification"
"$VENV/bin/ywd1278d" --config "$CONFIG" --framework-self-test
systemctl disable ywd-1278-install-resume.service >/dev/null 2>&1 || true
rm -f "$STATE_FILE"
date -u +'%Y-%m-%dT%H:%M:%SZ' >/var/lib/ywd-1278/install-complete
ok "YWD-1278 installation resumed and completed"
info "The packet service remains disabled until its packet engine/firmware stage is qualified."
echo "YWD1278_INSTALL_RESUME=PASS"
echo "RF_TRANSMITTED=NO"
echo "FLASH_WRITTEN=NO"
