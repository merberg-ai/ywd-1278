#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bootstrap = (ROOT / "installer" / "bootstrap.sh").read_text(encoding="utf-8")
ui = (ROOT / "installer" / "lib" / "ui.sh").read_text(encoding="utf-8")

# The public install command is intentionally curl-piped. The bootstrap must
# reconnect the full installer to the controlling terminal so interactive setup
# cannot consume the curl stream as stdin.
assert "exec 3</dev/tty" in bootstrap
assert 'bash "$tmp/repo/installer/install.sh" "${FORWARD[@]}" <&3' in bootstrap

# Shared UI prompts independently retain the same protection for any installer
# subcommand launched with redirected stdin.
assert "_ywd_read(){" in ui
assert "exec 9</dev/tty" in ui
assert "_ywd_read value || value=''" in ui
assert ui.count("_ywd_read answer") >= 2

# Exact confirmations must remain fail-closed when no input source exists.
assert "_ywd_read answer || return 1" in ui

print("INSTALLER_PIPED_PROMPT_CONTRACT=PASS")
print("BOOTSTRAP_CONTROLLING_TTY=PASS")
print("SHARED_UI_TTY_FALLBACK=PASS")
