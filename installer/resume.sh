#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root

STATE_FILE=/var/lib/ywd-1278/install-resume.env
PENDING_FILE=/var/lib/ywd-1278/install-interactive-pending
INSTALL_LOG=/var/log/ywd-1278/install.log
AUTOMATIC=0
[[ "${1:-}" == --automatic ]] && AUTOMATIC=1

init_log "$INSTALL_LOG"

[[ -f "$STATE_FILE" ]] || {
  if [[ $AUTOMATIC -eq 0 ]]; then info "No interrupted YWD-1278 installation needs resuming."; fi
  exit 0
}
# Root-created state contains only installer-owned assignments.
# shellcheck disable=SC1090
source "$STATE_FILE"
DEVICE="${DEVICE:-/dev/ttyAMA0}"
RUN_SETUP="${RUN_SETUP:-1}"
BUILD_USER="${BUILD_USER:-}"
ALLOW_CANDIDATE_RELEASE="${ALLOW_CANDIDATE_RELEASE:-0}"

banner
stage "Resume YWD-1278 installation"
section "Verify Raspberry Pi UART repair"
if ! capture_logged audit "Post-reboot UART audit" bash "$SOURCE_ROOT/installer/platform.sh" audit; then
  die "UART audit failed after reboot; installation state has been preserved"
fi
grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" || die "UART is still not ready after reboot; installation state has been preserved"
grep -q '^SERIAL_CONSOLE_PRESENT=NO$' <<<"$audit" || die "Serial console still owns the modem UART; installation state has been preserved"
ok "Radio UART repair is complete"

touch "$PENDING_FILE"
chmod 0600 "$PENDING_FILE"
systemctl disable ywd-1278-install-resume.service >/dev/null 2>&1 || true
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true

if [[ $AUTOMATIC -eq 1 ]]; then
  warn "Interactive radio HAT and station setup is still required"
  info "Reconnect to this Raspberry Pi and run: sudo $SOURCE_ROOT/installer/resume.sh"
  record_marker "YWD1278_INSTALL_RESUME_PLATFORM=PASS"
  record_marker "INTERACTIVE_CONTINUATION_REQUIRED=YES"
  record_marker "SERVICE_ENABLED=NO"
  record_marker "RF_TRANSMITTED=NO"
  record_marker "FLASH_WRITTEN=NO"
  exit 0
fi

section "Continue interactive setup"
info "Continuing at radio HAT qualification; no firmware write occurred during boot resume"
continue_args=()
[[ "$RUN_SETUP" == 1 ]] && continue_args+=(--setup) || continue_args+=(--no-setup)
[[ -z "$BUILD_USER" ]] || continue_args+=(--build-user "$BUILD_USER")
[[ "$ALLOW_CANDIDATE_RELEASE" == 1 ]] && continue_args+=(--allow-candidate-release)

YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/continue-install.sh" "${continue_args[@]}"

rm -f "$STATE_FILE" "$PENDING_FILE"
ok "Saved installation continuation completed"
record_marker "YWD1278_INSTALL_RESUME=PASS"
