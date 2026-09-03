#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, verify_fcs  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402

TARGETS = ROOT / "firmware" / "targets.json"
ORIGINAL_STAGE = ROOT / "firmware" / "qualification" / "p13b-single-tx.json"
STAGING = ROOT / "firmware" / "qualification" / "p13b-r1-three-tx.json"
ORIGINAL_TOOL = ROOT / "tools" / "qualify_single_tx.py"
TOOL = ROOT / "tools" / "qualify_tx_sequence.py"
KISS_SERVER = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
original_stage = json.loads(ORIGINAL_STAGE.read_text(encoding="utf-8"))
stage = json.loads(STAGING.read_text(encoding="utf-8"))
original_tool = ORIGINAL_TOOL.read_text(encoding="utf-8")
tool = TOOL.read_text(encoding="utf-8")
kiss = KISS_SERVER.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

# R1 is retained exactly as the historical partial physical attempt. P13b was
# ultimately qualified by R2; the current target has since advanced through P2
# while P12b, one-shot, R1, and R2 evidence remain frozen rather than rewritten.
assert target["status"] == "0c-p2-channel-busy-detector-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
assert target["packet_live_rf_kiss_qualification"]["receive_frequency_hz"] == 145050000
assert target["packet_live_tx_qualification"]["status"] == "qualified"
assert target["channel_busy_qualification"]["status"] == "host-qualified"
assert target["channel_busy_qualification"]["kiss_tx_connected"] is False

# Preserve the exact original one-shot staging vector and tool rather than
# silently repurposing the already-executed test.
assert original_stage["phase"] == "0B-P13b"
assert original_stage["status"] == "staged"
assert original_stage["maximum_transmissions"] == 1
assert original_stage["information_text"] == "YWD-1278 P13B SINGLE TX TEST"
assert original_stage["frame_sha256"] == "06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87"
assert original_stage["selector_count"] == 753
assert original_stage["expected_generated_samples_delta"] == 12048
assert 'P13B_CONFIRMATION_TOKEN = "P13B-145050-ONE-SHOT"' in original_tool
assert 'print("YWD1278_0B_P13B_INTERNAL_SINGLE_TX=PASS")' in original_tool

expected_stage = {
    "schema": 1,
    "phase": "0B-P13b-R1",
    "status": "staged",
    "purpose": "external-decode-assist",
    "target_id": "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021",
    "transmit_frequency_hz": 145050000,
    "source": "KJ6YWD-10",
    "destination": "YWD13B",
    "frame_type": "UI",
    "pid": "0xF0",
    "pre_flags": 45,
    "post_flags": 3,
    "initial_tone": "MARK",
    "samples_per_selector": 16,
    "inter_packet_pause_seconds": 5.0,
    "maximum_transmissions": 3,
    "retry_transmit_on_failure": False,
    "expected_keyup_delta": 3,
    "expected_generated_samples_delta": 34608,
    "requires_exact_packet_identity": True,
    "requires_idle_modem": True,
    "requires_external_decode": True,
    "minimum_external_decodes_required": 1,
    "kiss_tx_connected": False,
    "product_tx_enabled": False,
    "flash_permitted": False,
    "gpio_reset_permitted": False,
    "option_bytes_permitted": False,
    "confirmation_token": "P13B-R1-145050-VERIFY-3",
    "frames": [
        {
            "sequence": 1,
            "information_text": "YWD-1278 P13B VERIFY 1/3",
            "frame_bytes": 42,
            "frame_hex": "b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920312f3373a3",
            "frame_sha256": "f2e11d43587cab7b30d3bfafeb178b42ba3635a89b25902bc4d126c3e05b6ab2",
            "selector_count": 721,
            "packed_selector_bytes": 91,
            "packed_selector_sha256": "9abce15293666e5718011191ebaa4fa9e7e4cdf0ff24b14a24b527a0e1184e04",
            "expected_generated_samples": 11536,
        },
        {
            "sequence": 2,
            "information_text": "YWD-1278 P13B VERIFY 2/3",
            "frame_bytes": 42,
            "frame_hex": "b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920322f33174c",
            "frame_sha256": "777cae2a3d70d5e458bd8fd8fde9165a4e0ac158e1ecf48d2ca8d3ca90fcccc4",
            "selector_count": 721,
            "packed_selector_bytes": 91,
            "packed_selector_sha256": "b5e2bc3485c433fd3722860b14759269a6ce150d6f864c51018f2428938c102b",
            "expected_generated_samples": 11536,
        },
        {
            "sequence": 3,
            "information_text": "YWD-1278 P13B VERIFY 3/3",
            "frame_bytes": 42,
            "frame_hex": "b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920332f33cb16",
            "frame_sha256": "e79795fceb05569fcb825ac9e98cf3b5decd08a3185ca31c5f9851b39920b321",
            "selector_count": 721,
            "packed_selector_bytes": 91,
            "packed_selector_sha256": "080d92f1e6db8d0a1fd24ba61ed6cd06601d6e548d124f262b7ebb029f5b687a",
            "expected_generated_samples": 11536,
        },
    ],
}
assert stage == expected_stage

# Independently reconstruct and lock all three historical R1 AX.25/P5 vectors.
for vector in stage["frames"]:
    frame = build_ui_frame(
        source=Address.parse(stage["source"]),
        destination=Address.parse(stage["destination"]),
        info=vector["information_text"].encode("ascii"),
        include_fcs=True,
    )
    assert verify_fcs(frame)
    assert len(frame) == 42
    assert frame.hex() == vector["frame_hex"]
    assert hashlib.sha256(frame).hexdigest() == vector["frame_sha256"]
    selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3, initial_tone=MARK)
    packed = pack_selectors(selectors)
    assert len(selectors) == 721
    assert len(packed) == 91
    assert hashlib.sha256(packed).hexdigest() == vector["packed_selector_sha256"]
    assert len(selectors) * 16 == 11536
assert sum(item["expected_generated_samples"] for item in stage["frames"]) == 34608

# R1 has only two operator arguments: dry-run/transmit mode and the exact
# confirmation token. Target, UART, frequency, payloads, count, and timing are
# hard-coded/frozen and cannot be selected on the command line.
assert 'TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"' in tool
assert 'DEVICE = "/dev/ttyAMA0"' in tool
assert 'P13B_FREQUENCY_HZ = 145050000' in tool
assert 'P13B_R1_CONFIRMATION_TOKEN = "P13B-R1-145050-VERIFY-3"' in tool
assert 'ap.add_argument("--transmit", action="store_true")' in tool
assert 'ap.add_argument("--confirm", default="")' in tool
for forbidden_arg in (
    '--target', '--device', '--frequency', '--source', '--destination',
    '--payload', '--count', '--pause', '--staging', '--targets'
):
    assert forbidden_arg not in tool, forbidden_arg

assert 'if not isinstance(frames, list) or len(frames) != 3:' in tool
assert 'stage.get("maximum_transmissions") != 3' in tool
assert 'stage.get("inter_packet_pause_seconds") != 5.0' in tool
assert 'for index, (vector, frame) in enumerate(vectors, start=1):' in tool
assert tool.count("broker.submit_frame(") == 1
assert "Never retry a failed call" in tool
assert 'time.sleep(stage["inter_packet_pause_seconds"])' in tool
assert 'transmit_submissions != stage["maximum_transmissions"]' in tool
assert 'keyup_delta != stage["expected_keyup_delta"]' in tool
assert 'generated_delta != stage["expected_generated_samples_delta"]' in tool
assert 'queue_capacity=1' in tool
assert 'transmit_enabled=True' in tool

# These assertions intentionally preserve the R1 checker implementation that
# produced the known false-negative. R2 corrects the diagnostic semantics; R1
# is historical evidence and must not be silently rewritten.
assert 'if burst_keyups != 1:' in tool
assert 'if burst_samples != vector["expected_generated_samples"]:' in tool
assert 'print(f"BURST[{index}]_RF_KEYUP_DELTA={burst_keyups}")' in tool
assert 'print(f"BURST[{index}]_GENERATED_SAMPLES_DELTA={burst_samples}")' in tool
assert 'print(f"PAUSE_AFTER[{index}]={stage[\'inter_packet_pause_seconds\']:.1f}s")' in tool

# Dry-run exits before owner/UART construction. The real path still goes only
# through TXModemOwner + P13a TXBroker and uses the original simplex setup.
dry_run_pos = tool.index('if not args.transmit:')
owner_construct_pos = tool.index('owner = TXModemOwner(')
assert dry_run_pos < owner_construct_pos
assert 'posix_serial_transport_factory(DEVICE)' in tool
assert 'owner.get_version' in tool
assert 'owner.set_rx_frequency(P13B_FREQUENCY_HZ' in tool
assert 'owner.arm_rx_modem_io' in tool
assert 'print("P13B_R1_DRY_RUN=PASS")' in tool
assert 'print("HARDWARE_UART_OPENED=NO")' in tool
assert 'print("RF_TRANSMITTED=NO")' in tool
assert 'print("YWD1278_0B_P13B_R1_INTERNAL_THREE_TX=PASS")' in tool

# No raw modem, abort/exit, flash, GPIO/reset, option-byte, KISS, daemon, or
# persistent service escape hatch is introduced.
for forbidden in (
    "rf_abort_request",
    "rf_exit_request",
    "stm32flash",
    "pinctrl",
    "0x1FFFF800",
    "0x1ffff800",
    "0x1FFFF7E0",
    "0x1ffff7e0",
    ".transact(",
):
    assert forbidden not in tool, forbidden
for forbidden in ("TXBroker", "TXModemOwner", "transmit_selector_burst", "RF_TX_TONES"):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("P13B_R1_THREE_TX_CONTRACT=PASS")
print("ORIGINAL_P13B_ONE_SHOT_PRESERVED=PASS")
print("P13B_R1_HISTORICAL_PARTIAL_ATTEMPT=PASS")
print("P2_CURRENT_TARGET_BOUNDARY=QUALIFIED")
print("P13B_R1_FREQUENCY_HZ=145050000")
print("P13B_R1_FIXED_FRAMES=3")
print("P13B_R1_SELECTOR_COUNT_EACH=721")
print("P13B_R1_SAMPLES_EACH=11536")
print("P13B_R1_INTER_PACKET_PAUSE_SECONDS=5.0")
print("AUTOMATIC_TX_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
