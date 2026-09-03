#!/usr/bin/env python3
"""Static and manifest contract for the guarded 0C-P4e live multi-cycle gate."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "qualify_live_p4e_multicycle.py"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p4e-live-multicycle.json"

source = HARNESS.read_text(encoding="utf-8")
stage = json.loads(MANIFEST.read_text(encoding="utf-8"))
tree = ast.parse(source)

assert stage["phase"] == "0C-P4e-live"
assert stage["status"] == "staged"
assert stage["base_checkpoint"] == "checkpoint/0c-p4e-persistent-half-duplex-host-qualified"
assert stage["base_checkpoint_sha"] == "0257f9947aea60d943b6b6b52e2ad7d9e28766de"
assert stage["device"] == "/dev/ttyAMA0"
assert stage["frequency_hz"] == 145_050_000
assert stage["rf_power"] == 200
assert stage["cycles"] == 3
assert stage["maximum_transmit_submissions"] == 3
assert stage["automatic_tx_retry"] is False
assert stage["requires_fresh_fcs_valid_rx_trigger_before_each_tx"] is True
assert stage["required_pre_tx_decoded_frames"] == 3
assert stage["requires_live_busy_before_each_tx"] is True
assert stage["requires_final_fcs_valid_rx_after_cycle_3_restart"] is True
assert stage["required_total_inbound_decoded_frames"] == 4
assert stage["requires_external_decode_of_all_outgoing_frames"] is True
assert stage["required_external_tx_decodes"] == 3
assert stage["qualification_randomness"] == {
    "before_fresh_decoded_busy_trigger": 255,
    "after_fresh_decoded_busy_trigger": [255, 0],
}
assert stage["kiss_tx_connected"] is False
assert stage["product_tx_enabled"] is False
assert stage["flash_permitted"] is False
assert stage["gpio_reset_permitted"] is False
assert stage["option_bytes_permitted"] is False

expected_vectors = [
    (
        1,
        "YWD-1278 P4E CYCLE 1/3",
        40,
        705,
        89,
        "6aac46f53fb71633e7b103aa97644eecd68e3c1a07c437e594c018e1b1700b03",
        11280,
    ),
    (
        2,
        "YWD-1278 P4E CYCLE 2/3",
        40,
        705,
        89,
        "c162c20d54180885d8b842b6922e4afb157dd1dec4fb514d378a39ba7f1e65a4",
        11280,
    ),
    (
        3,
        "YWD-1278 P4E CYCLE 3/3",
        40,
        705,
        89,
        "715b21aadabc4b4fbb019c5cd44a333fe754d7a099d53a70955842dc14e92f65",
        11280,
    ),
]
assert len(stage["frames"]) == len(expected_vectors)
for vector, expected in zip(stage["frames"], expected_vectors):
    actual = (
        vector["cycle"],
        vector["information_text"],
        vector["frame_bytes"],
        vector["selector_count"],
        vector["packed_selector_bytes"],
        vector["packed_selector_sha256"],
        vector["expected_generated_samples"],
    )
    assert actual == expected

# No arbitrary physical profile or payload/count/retry controls are exposed.
parser_options = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "add_argument" and node.args and isinstance(node.args[0], ast.Constant):
            parser_options.append(node.args[0].value)
assert parser_options == ["--transmit", "--confirm"], parser_options
for forbidden in (
    "--frequency",
    "--frequency-hz",
    "--power",
    "--payload",
    "--frame",
    "--count",
    "--retry",
    "--device",
):
    assert forbidden not in parser_options

# Default/dry-run exits before owner construction and therefore before UART.
assert source.index("if not args.transmit:") < source.index("owner = TXModemOwner(")
assert source.index("if args.confirm != CONFIRMATION_TOKEN:") < source.index("owner = TXModemOwner(")
assert source.index("typed = input(") < source.index("owner = TXModemOwner(")
assert "P4E_LIVE_DRY_RUN=PASS" in source
assert "TX_MODEM_OWNER_CONSTRUCTED=NO" in source
assert "HARDWARE_UART_OPENED=NO" in source

# The physical graph must use the qualified persistent lifecycle behind P4a.
assert "PersistentHalfDuplexSubmitter(" in source
assert "BoundedChannelAccessQueue(" in source
assert "TXBroker(" in source
assert "TXModemOwner(" in source
assert "posix_serial_transport_factory" in source
assert "access_queue = BoundedChannelAccessQueue(" in source
assert "lifecycle," in source
assert "broker.submit_frame(" not in source
assert "transmit_selector_burst(" not in source
assert "rf_tx_tones_request(" not in source

# Every outgoing cycle starts with a fresh decoder on active RX, and no access
# request can deliberately pass PERSIST until both live BUSY and a decoded frame
# have occurred during that cycle.
assert "for cycle_index, (frame, vector)" in source
assert "decoder = StreamingBell202Decoder()" in source
assert "if not (seen_busy and decoded_trigger):" in source
assert "pre_trigger_defers += 1" in source
assert "return 255" in source
assert "post_trigger_trials == 1" in source
assert "post_trigger_trials == 2" in source
assert "if not seen_busy or not decoded_trigger:" in source
assert "cycle {cycle_index} reached downstream before fresh decoded BUSY trigger" in source

# The lifecycle returns only after RX restart. The harness then proves typed RX
# status and reset-on-accept TX diagnostics for each of the three fixed bursts.
assert "require_active_rx(restarted, context=f\"after cycle {cycle_index} TX restart\")" in source
assert "diag.keyups != 1" in source
assert "diag.generated_samples != vector[\"expected_generated_samples\"]" in source
assert "lifecycle.snapshot" in source
assert "snap.cycles_completed != cycle_index" in source

# Two complete P1 full slots remain required around the deterministic 255/0
# trials; the physical timeline is checked rather than merely printed.
assert "defer_elapsed - clear_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS" in source
assert "dispatch_elapsed - defer_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS" in source

# After cycle 3 there is no queued request. A fresh decoder must receive a
# fourth FCS-valid inbound frame before execution can pass.
assert "access_queue.snapshot.queue_depth != 0" in source
assert "final_decoder = StreamingBell202Decoder()" in source
assert "FINAL_POST_TX_RX_WINDOW=OPEN" in source
assert "final post-cycle-3 RX restart did not decode a fresh FCS-valid AX.25 frame" in source
assert "FINAL_POST_TX_FCS_VALID_RX=PASS" in source

# Post-TX failures must never be mislabeled as zero-TX/safe-to-rerun. Physical
# acceptance is recovered from both the P4e lifecycle and broker snapshots.
assert "lifecycle.snapshot.downstream_accepted" in source
assert "broker.snapshot.accepted" in source
assert "P4E_LIVE_ACCEPTED_TX_BEFORE_FAILURE" in source
assert "DO_NOT_RERUN_FULL_P4E_LIVE_HARNESS=YES" in source
assert "AUTOMATIC_TX_RETRY=NO" in source
assert "DUPLICATE_DISPATCH=NO" in source

# No firmware mutation or external product TX surface belongs to this gate.
for forbidden in (
    "stm32flash",
    "HAT_BOOTLOADER",
    "option byte",
    "gpiod",
    "RPi.GPIO",
    "KISSServer",
    "kiss_server",
):
    assert forbidden not in source

print("P4E_LIVE_MULTICYCLE_CONTRACT=PASS")
print("FIXED_TX_FRAMES=3")
print("REQUIRED_INBOUND_FCS_VALID_FRAMES=4")
print("POST_TX_FINAL_RX_PROOF=REQUIRED")
print("EXTERNAL_TX_DECODES_REQUIRED=3")
print("AUTOMATIC_TX_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("FLASH_GPIO_OPTION_BYTES=ABSENT")
