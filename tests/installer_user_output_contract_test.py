#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bootstrap = (ROOT / "installer" / "bootstrap.sh").read_text(encoding="utf-8")
install = (ROOT / "installer" / "install.sh").read_text(encoding="utf-8")
ui = (ROOT / "installer" / "lib" / "ui.sh").read_text(encoding="utf-8")

# Normal installation output is human-facing. Exact qualification/evidence
# markers remain available in the persistent log and optional machine-output
# mode instead of being dumped into an interactive terminal.
assert 'INSTALL_LOG="$LOG_DIR/install.log"' in install
assert 'init_log "$INSTALL_LOG"' in install
assert 'record_marker "YWD1278_INSTALL=PASS"' in install
assert 'record_marker "SERVICE_ENABLED=NO"' in install
assert 'record_marker "RF_TRANSMITTED=NO"' in install
assert 'record_marker "FLASH_WRITTEN=NO"' in install
assert 'echo "YWD1278_INSTALL=PASS"' not in install
assert 'echo "SERVICE_ENABLED=NO"' not in install
assert 'echo "RF_TRANSMITTED=NO"' not in install
assert 'echo "FLASH_WRITTEN=NO"' not in install

# Verbose package/tool output and raw hardware/readiness marker blocks go to
# install.log; the terminal gets concise [OK]/[INFO]/[WARN]/[FAIL] summaries.
assert 'run_logged "Refreshing package information" apt-get update' in install
assert 'run_logged "Installing required packages" apt-get install' in install
assert 'run_logged "Checking installed runtime"' in install
assert 'capture_logged audit "Raspberry Pi UART audit"' in install
assert 'log_block "HAT detection"' in install
assert 'log_block "Product runtime readiness"' in install
assert 'printf \'%s\\n\' "$audit"' not in install
assert 'printf \'%s\\n\' "$readiness"' not in install

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
