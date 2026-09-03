#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p4d-live-csma-single-tx.json"
HARNESS = ROOT / "tools" / "qualify_live_csma_single_tx.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
harness = HARNESS.read_text(encoding="utf-8")
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

assert manifest["schema"] == 1
assert manifest["phase"] == "0C-P4d"
assert manifest["status"] == "staged"
assert manifest["base_checkpoint"] == "checkpoint/0c-p4c-real-owner-fake-transport-qualified"
assert manifest["base_checkpoint_sha"] == "e137b98b86b70b6835990c35f192741f0cb496e8"
assert manifest["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert manifest["device"] == "/dev/ttyAMA0"
assert manifest["runtime_identity"] == (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
assert manifest["transmit_frequency_hz"] == 145050000
assert manifest["rf_power"] == 200
assert manifest["source"] == "KJ6YWD-10"
assert manifest["destination"] == "YWD4D"
assert manifest["information_text"] == "YWD-1278 P4D CSMA VERIFY 1/1"
assert manifest["frame_bytes"] == 46
assert manifest["frame_hex"] == "b2ae88688840e096946cb2ae887503f05957442d31323738205034442043534d412056455249465920312f310a32"
assert manifest["frame_sha256"] == "2f700a4dd7675473a183e119b711ed44c1f0a1ed3a70505523c63af8d42d6655"
assert manifest["pre_flags"] == 45
assert manifest["post_flags"] == 3
assert manifest["initial_tone"] == "MARK"
assert manifest["selector_count"] == 753
assert manifest["packed_selector_bytes"] == 95
assert manifest["packed_selector_sha256"] == "ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca"
assert manifest["samples_per_selector"] == 16
assert manifest["expected_generated_samples"] == 12048
assert manifest["detector"] == {
    "busy_assert_raw_max": 83,
    "clear_release_raw_min": 90,
    "recent_rx_hold_seconds": 0.25,
}
assert manifest["csma"] == {
    "persist": 63,
    "slot_time_10ms": 10,
    "slot_seconds": 0.1,
    "maximum_wait_seconds": 30.0,
}
assert manifest["qualification_randomness"] == {
    "before_first_live_busy": 255,
    "post_busy_sequence": [255, 0],
}
assert manifest["requires_live_busy_before_dispatch"] is True
assert manifest["maximum_transmit_submissions"] == 1
assert manifest["automatic_tx_retry"] is False
assert manifest["requires_external_decode"] is True
assert manifest["minimum_external_decodes_required"] == 1
assert manifest["confirmation_token"] == "P4D-145050-P200-CSMA-VERIFY-1"
assert manifest["interactive_confirmation"] == "TRANSMIT-P4D-CSMA-VERIFY-ONE"
for key in (
    "kiss_tx_connected",
    "daemon_tx_connected",
    "product_tx_enabled",
    "flash_permitted",
    "gpio_reset_permitted",
    "option_bytes_permitted",
):
    assert manifest[key] is False, key

# The fixed live graph must be the already-qualified queue/broker/owner stack over
# the real POSIX transport. There is no qualification-only raw TX shortcut.
for required in (
    "TXModemOwner(",
    "posix_serial_transport_factory(DEVICE)",
    "TXBroker(",
    "BoundedChannelAccessQueue(",
    "owner.rx_rssi(timeout=1.25)",
    "owner.apply_tx_qualification_profile(timeout=1.5)",
    "owner.arm_rx_modem_io(timeout=1.5)",
    "if not seen_busy:",
    "return 255",
    "if post_busy_trials == 1:",
    "if post_busy_trials == 2:",
    "P4d downstream TX was reached before required live BUSY",
    "TRANSMIT_SUBMISSIONS=1",
    "RF_TRANSMITTED=YES_EXACTLY_ONE_BURST",
    "QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DECODE",
):
    assert required in harness, required

# Dry-run must exit before the real owner construction and physical mode must be
# gated by both exact CLI and interactive confirmations.
dry_index = harness.index("if not args.transmit:")
owner_index = harness.index("owner = TXModemOwner(")
assert dry_index < owner_index
assert "if args.confirm != CONFIRMATION_TOKEN:" in harness
assert "typed = input(" in harness
assert "if typed != INTERACTIVE_CONFIRMATION:" in harness
assert harness.index("if args.confirm != CONFIRMATION_TOKEN:") < owner_index
assert harness.index("if typed != INTERACTIVE_CONFIRMATION:") < owner_index

# No operator-tunable RF/payload/count surface is allowed in this one-purpose
# harness. Only --transmit and --confirm are accepted arguments.
tree = ast.parse(harness)
argument_names: list[str] = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            argument_names.append(node.args[0].value)
assert sorted(argument_names) == ["--confirm", "--transmit"]
for forbidden in (
    "--frequency",
    "--frequency-hz",
    "--power",
    "--payload",
    "--frame",
    "--count",
    "--repeat",
    "--retry",
    "--device",
):
    assert forbidden not in argument_names

# The physical harness may use fuser only to prove UART ownership is free. It
# must not import flash/GPIO helpers, KISS/network input, or shell out to a TX
# utility.
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        assert "kiss" not in module
        assert "firmware" not in module
        assert "gpio" not in module.lower()
    elif isinstance(node, ast.Import):
        for alias in node.names:
            assert alias.name not in {"socket", "gpiod", "RPi.GPIO"}, alias.name
assert '["fuser", DEVICE]' in harness
assert "stm32flash" not in harness
assert "pinctrl" not in harness

# One-shot diagnostics are exact and use the inherited reset-on-accepted-burst
# semantics. No loop or helper may retry broker.submit_frame().
assert "post_diag.keyups != 1" in harness
assert "post_diag.generated_samples != stage[\"expected_generated_samples\"]" in harness
assert "broker.snapshot.submitted != 1 or broker.snapshot.accepted != 1" in harness
assert "automatic retry" not in harness.lower().replace("no automatic retry", "")

# Ordinary product/KISS inputs remain disconnected from all TX-capable layers.
for forbidden in (
    "BoundedChannelAccessQueue",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("P4D_LIVE_CSMA_SINGLE_TX_CONTRACT=PASS")
print("BASE_CHECKPOINT=0C-P4C_QUALIFIED")
print("FIXED_PACKET=KJ6YWD-10>YWD4D:YWD-1278_P4D_CSMA_VERIFY_1/1")
print("LIVE_BUSY_BEFORE_TX=REQUIRED")
print("MAXIMUM_TX_SUBMISSIONS=1")
print("AUTOMATIC_TX_RETRY=NO")
print("POSIX_SERIAL_TRANSPORT=PHYSICAL_MODE_ONLY")
print("DRY_RUN_UART_OPEN=NO")
print("EXTERNAL_DECODE_REQUIRED=YES")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("FLASH_GPIO_OPTION_BYTES=FORBIDDEN")
