#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bootstrap = (ROOT / "installer" / "bootstrap.sh").read_text(encoding="utf-8")
install = (ROOT / "installer" / "install.sh").read_text(encoding="utf-8")
continuation = (ROOT / "installer" / "continue-install.sh").read_text(encoding="utf-8")
hat = (ROOT / "installer" / "setup-hat.sh").read_text(encoding="utf-8")
finalizer = (ROOT / "installer" / "finalize-product-service.sh").read_text(encoding="utf-8")
ui = (ROOT / "installer" / "lib" / "ui.sh").read_text(encoding="utf-8")

# Normal installation output is human-facing. Exact qualification/evidence
# markers remain available in the persistent log and optional machine-output
# mode instead of being dumped into an interactive terminal. Completion markers
# now belong to the shared post-UART continuation rather than install.sh.
assert 'INSTALL_LOG="$LOG_DIR/install.log"' in install
assert 'init_log "$INSTALL_LOG"' in install
assert 'record_marker "YWD1278_INSTALL=PASS"' in continuation
assert 'record_marker "SERVICE_ENABLED=$service_enabled"' in continuation
assert 'record_marker "RF_TRANSMITTED=NO"' in continuation
assert 'echo "YWD1278_INSTALL=PASS"' not in install + continuation
assert 'echo "SERVICE_ENABLED=NO"' not in install + continuation
assert 'echo "RF_TRANSMITTED=NO"' not in install + continuation

# Verbose package/tool output and raw UART/HAT/readiness marker blocks go to the
# installation log; the terminal gets concise [OK]/[INFO]/[WARN]/[FAIL] summaries.
assert 'run_logged "Refreshing package information" apt-get update' in install
assert 'run_logged "Installing required packages" apt-get install' in install
assert 'run_logged "Checking installed runtime"' in install
assert 'capture_logged audit "Raspberry Pi UART audit"' in install
assert 'log_block "Guided HAT detection"' in hat
assert 'log_block "Hardware qualification recheck"' in hat
assert 'capture_logged readiness "Post-setup runtime readiness"' in continuation
assert 'capture_logged readiness "Final runtime readiness"' in finalizer
assert 'printf \'%s\\n\' "$audit"' not in install
assert 'printf \'%s\\n\' "$readiness"' not in continuation

# Shared UI owns colors/status semantics and machine/log routing.
for token in (
    "YWD_PURPLE",
    "stage(){",
    "init_log(){",
    "log_block(){",
    "record_marker(){",
    "run_logged(){",
    "capture_logged(){",
):
    assert token in ui
assert 'YWD1278_MACHINE_OUTPUT:-0' in ui

# Bootstrap is also quiet and sends clone/package detail into the same log,
# while preserving the controlling-TTY handoff for interactive questions.
assert 'INSTALL_LOG="$LOG_DIR/install.log"' in bootstrap
assert 'git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$tmp/repo" >>"$INSTALL_LOG" 2>&1' in bootstrap
assert "exec 3</dev/tty" in bootstrap
assert 'bash "$tmp/repo/installer/install.sh" "${FORWARD[@]}" <&3' in bootstrap

print("INSTALLER_USER_OUTPUT_CONTRACT=PASS")
print("INSTALL_LOGGING=PASS")
print("HUMAN_STDOUT=PASS")
print("MACHINE_MARKERS_RETAINED=PASS")
