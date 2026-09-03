#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVATE = ROOT / "firmware" / "activate-rssi-live.sh"
text = ACTIVATE.read_text(encoding="utf-8")

# readback_prefix_sha() is used inside command substitution. stm32flash emits
# informational text on stdout, so that output must be redirected away from
# stdout or it contaminates the returned SHA256 string.
needle = 'stm32flash -b 115200 -r "$tmp" -S "$flash_base:$bytes" "$DEVICE" >&2 || { rm -f "$tmp"; return 1; }'
assert needle in text

# The physical preflight false-negative from attempt 1 must remain documented.
doc = (ROOT / "docs" / "qualifications" / "0c-p2-live-rssi-preflight-attempt-1-2026-09-02.md").read_text(encoding="utf-8")
assert "PRE-WRITE FALSE NEGATIVE" in doc
assert "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310" in doc
assert "AX25R4 candidate write attempted: NO" in doc

print("P2_READBACK_STDOUT_CONTRACT=PASS")
print("STM32FLASH_READBACK_STDOUT_REDIRECTED=YES")
print("PREFLIGHT_ATTEMPT_1_PRESERVED=YES")
print("RF_TRANSMITTED_BY_CI=NO")
