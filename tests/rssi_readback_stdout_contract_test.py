#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "firmware" / "activate-rssi-live.sh"
R2 = ROOT / "firmware" / "activate-rssi-live-r2.sh"
base = BASE.read_text(encoding="utf-8")
r2 = R2.read_text(encoding="utf-8")

# Attempt 1 remains historical and unchanged: its readback helper calls
# stm32flash directly while inside command substitution.
assert 'readback_prefix_sha(){' in base
assert 'stm32flash -b 115200 -r "$tmp" -S "$flash_base:$bytes" "$DEVICE"' in base

# R2 changes only the stm32flash process boundary. Every -r invocation has its
# informational stdout redirected to stderr, allowing the base helper's
# sha256sum output to remain the only captured stdout value.
for required in (
    'BASE_HARNESS="$SCRIPT_DIR/activate-rssi-live.sh"',
    'YWD1278_REAL_STM32FLASH="$(command -v stm32flash || true)"',
    'if [[ "$arg" == "-r" ]]',
    'command "$YWD1278_REAL_STM32FLASH" "$@" >&2',
    'command "$YWD1278_REAL_STM32FLASH" "$@"',
    'export -f stm32flash',
    'exec bash "$BASE_HARNESS" "$@"',
):
    assert required in r2, required

# R2 must not add any physical controls or weaken the frozen base harness.
for forbidden in (
    "stm32flash -w",
    "pinctrl",
    "raspi-gpio",
    "TXModemOwner",
    "TXBroker",
    "transmit_selector_burst",
    "--frequency-hz",
    "--device",
    "--firmware",
    "--threshold",
    "--hysteresis",
):
    assert forbidden not in r2, forbidden

# The physical preflight false-negative from attempt 1 must remain documented.
doc = (ROOT / "docs" / "qualifications" / "0c-p2-live-rssi-preflight-attempt-1-2026-09-02.md").read_text(encoding="utf-8")
assert "PRE-WRITE FALSE NEGATIVE" in doc
assert "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310" in doc
assert "AX25R4 candidate write attempted: NO" in doc

print("P2_R2_READBACK_STDOUT_CONTRACT=PASS")
print("ATTEMPT1_HARNESS_PRESERVED=YES")
print("R2_STM32FLASH_READ_STDOUT_TO_STDERR=YES")
print("R2_FLASH_LOGIC_CHANGED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
