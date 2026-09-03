#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "qualify_live_csma_single_tx_r2.py"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p4d-r2-live-csma-single-tx.json"
FROZEN_R1 = ROOT / "tools" / "qualify_live_csma_single_tx.py"

text = HARNESS.read_text(encoding="utf-8")
r1 = FROZEN_R1.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

assert manifest["phase"] == "0C-P4d-R2"
assert manifest["status"] == "staged"
assert manifest["supersedes"] == "0C-P4d-R1"
assert manifest["r1_staged_checkpoint_sha"] == "d2ff131b989ad4fe81baa8a86067383e98e66c73"
assert manifest["frame_bytes"] == 46
assert manifest["selector_count"] == 753
assert manifest["packed_selector_bytes"] == 95
assert manifest["packed_selector_sha256"] == "ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca"
assert manifest["expected_generated_samples"] == 12048
assert manifest["maximum_transmit_submissions"] == 1
assert manifest["automatic_tx_retry"] is False
assert manifest["requires_live_busy_before_tx"] is True
assert manifest["rx_start_required_before_rssi"] is True
assert manifest["rx_fifo_drain_while_sampling"] is True
assert manifest["fifo_dropped_bytes_required"] == 0
assert manifest["half_duplex_handoff"] == "RX_STOP_AFTER_READY_BEFORE_BROKER_SUBMIT"
assert manifest["rx_must_be_inactive_before_tx_tones"] is True
assert manifest["external_decode_required"] is True
assert manifest["kiss_tx_connected"] is False
assert manifest["product_tx_enabled"] is False
assert manifest["flash_permitted"] is False
assert manifest["gpio_reset_permitted"] is False
assert manifest["option_bytes_permitted"] is False

# R2 must preserve R1 as historical evidence instead of mutating it in place.
assert "owner.arm_rx_modem_io(timeout=1.5)\n        status_armed" in r1
assert "owner.rx_start(timeout=1.5)" not in r1

for required in (
    "owner.rx_start(timeout=1.5)",
    "require_active_rx(active)",
    "chunk = owner.rx_read(RX_READ_MAXIMUM, timeout=1.25)",
    "rssi = owner.rx_rssi(timeout=1.25)",
    "class RXStopThenBrokerSubmitter",
    "self.owner.rx_stop(timeout=1.25)",
    "if after.flags & 0x01",
    "return self.broker.submit_frame(frame_with_fcs, timeout=timeout)",
    "BoundedChannelAccessQueue(\n            handoff,",
    "if not seen_busy:\n            pre_busy_trials += 1\n            return 255",
    "if post_busy_trials == 1:\n            return 255",
    "if post_busy_trials == 2:\n            return 0",
    "P4D_R2_DRY_RUN=PASS",
    "TX_MODEM_OWNER_CONSTRUCTED=NO",
    "YWD1278_0C_P4D_R2_LIVE_CSMA_SINGLE_TX_EXECUTION=PASS",
    "RX_STOP_AFTER_READY_BEFORE_BROKER=PASS",
    "RX_INACTIVE_BEFORE_TX_TONES=PASS",
    "FIFO_DROPPED_BYTES=",
    "TRANSMIT_SUBMISSIONS=1",
    "AUTOMATIC_TX_RETRY=NO",
    "QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DECODE",
):
    assert required in text, required

# No tunable physical transmit surface may be added. Physical parameters and
# payload remain staged constants; only the explicit arming switches exist.
tree = ast.parse(text)
arg_strings: list[str] = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "add_argument" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                arg_strings.append(first.value)
assert sorted(arg_strings) == ["--confirm", "--transmit"]

for forbidden in (
    "--frequency",
    "--power",
    "--payload",
    "--frame",
    "--count",
    "--retry",
    "socket",
    "KISSServer",
    "stm32flash",
    "pinctrl",
    "gpiod",
):
    assert forbidden not in text, forbidden

# RX_STOP is allowed only in the qualification handoff and cleanup; there is no
# RF_ABORT/RF_EXIT escape route and no direct raw modem transact call.
for forbidden in (
    "rf_abort",
    "rf_exit",
    "transmit_selector_burst(",
    ".transact(",
):
    assert forbidden not in text, forbidden

print("P4D_R2_HALF_DUPLEX_PHYSICAL_CONTRACT=PASS")
print("R1_PRESERVED=YES")
print("RX_START_BEFORE_RSSI=REQUIRED")
print("RX_FIFO_DRAIN=REQUIRED")
print("RX_STOP_AFTER_READY_BEFORE_BROKER=REQUIRED")
print("MAX_TX_SUBMISSIONS=1")
print("AUTOMATIC_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
