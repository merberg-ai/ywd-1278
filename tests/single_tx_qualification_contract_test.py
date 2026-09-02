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
STAGING = ROOT / "firmware" / "qualification" / "p13b-single-tx.json"
TOOL = ROOT / "tools" / "qualify_single_tx.py"
KISS_SERVER = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
stage = json.loads(STAGING.read_text(encoding="utf-8"))
tool = TOOL.read_text(encoding="utf-8")
kiss = KISS_SERVER.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

# The original one-shot remains a frozen historical vector even after P13b was
# ultimately qualified by the corrected R2 external-decode sequence.
assert target["status"] == "0b-p13b-known-packet-tx-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
p12b = target["packet_live_rf_kiss_qualification"]
assert p12b["phase"] == "0B-P12b"
assert p12b["status"] == "qualified"
assert p12b["receive_frequency_hz"] == 145050000
assert p12b["rf_transmitted"] is False
assert target["packet_live_tx_qualification"]["status"] == "qualified"

assert stage == {
    "schema": 1,
    "phase": "0B-P13b",
    "status": "staged",
    "target_id": "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021",
    "transmit_frequency_hz": 145050000,
    "source": "KJ6YWD-10",
    "destination": "YWD13B",
    "information_text": "YWD-1278 P13B SINGLE TX TEST",
    "frame_type": "UI",
    "pid": "0xF0",
    "frame_bytes": 46,
    "frame_hex": "b2ae88626684e096946cb2ae887503f05957442d3132373820503133422053494e474c4520545820544553545c59",
    "frame_sha256": "06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87",
    "pre_flags": 45,
    "post_flags": 3,
    "initial_tone": "MARK",
    "selector_count": 753,
    "packed_selector_bytes": 95,
    "packed_selector_sha256": "7b99563d208029084af0559484ed38afbced3d01e9ec28610883efb5931e88b1",
    "samples_per_selector": 16,
    "expected_generated_samples_delta": 12048,
    "maximum_transmissions": 1,
    "retry_transmit_on_failure": False,
    "requires_exact_packet_identity": True,
    "requires_idle_modem": True,
    "requires_external_decode": True,
    "kiss_tx_connected": False,
    "product_tx_enabled": False,
    "flash_permitted": False,
    "gpio_reset_permitted": False,
    "option_bytes_permitted": False,
    "confirmation_token": "P13B-145050-ONE-SHOT",
}

# Lock the exact packet and P5 serialization vector independently of the tool.
frame = build_ui_frame(
    source=Address.parse("KJ6YWD-10"),
    destination=Address.parse("YWD13B"),
    info=b"YWD-1278 P13B SINGLE TX TEST",
    include_fcs=True,
)
assert verify_fcs(frame)
assert len(frame) == 46
assert frame.hex() == stage["frame_hex"]
assert hashlib.sha256(frame).hexdigest() == stage["frame_sha256"]
selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3, initial_tone=MARK)
packed = pack_selectors(selectors)
assert len(selectors) == 753
assert len(packed) == 95
assert hashlib.sha256(packed).hexdigest() == stage["packed_selector_sha256"]
assert len(selectors) * 16 == stage["expected_generated_samples_delta"]

# The physical harness is deliberately one-shot and has no user-selectable RF
# frequency, callsign, payload, serializer timing, or transmit count.
assert 'P13B_FREQUENCY_HZ = 145050000' in tool
assert 'P13B_CONFIRMATION_TOKEN = "P13B-145050-ONE-SHOT"' in tool
assert 'ap.add_argument("--transmit", action="store_true")' in tool
assert 'ap.add_argument("--confirm", default="")' in tool
assert '--frequency' not in tool
assert '--source' not in tool
assert '--destination' not in tool
assert '--payload' not in tool
assert '--count' not in tool
assert tool.count("broker.submit_frame(") == 1
assert "Never retry this call" in tool
assert 'transmit_enabled=True' in tool
assert 'queue_capacity=1' in tool

# Real UART access remains exclusively through TXModemOwner and the private
# single-owner POSIX transport factory. Setup is the original frozen simplex profile.
assert "TXModemOwner(" in tool
assert "posix_serial_transport_factory(args.device)" in tool
assert "owner.get_version" in tool
assert "owner.rf_status" in tool
assert "owner.rf_diagnostics" in tool
assert "owner.set_rx_frequency(P13B_FREQUENCY_HZ" in tool
assert "owner.arm_rx_modem_io" in tool
assert "counter_delta(diag_before.keyups, diag_after.keyups, 1 << 8)" in tool
assert '1 << 16' in tool
assert 'stage["expected_generated_samples_delta"]' in tool
assert "uart_is_free(args.device)" in tool

# No escape hatch is added for looping, abort/exit, arbitrary modem frames,
# flash, GPIO/reset, option bytes, or KISS-originated TX.
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

# Dry-run is guaranteed to return before TXModemOwner construction/opening the
# serial transport. Independent receiver evidence was supplied by R2, not by
# retroactively changing this original one-shot harness.
dry_run_pos = tool.index('if not args.transmit:')
owner_construct_pos = tool.index('owner = TXModemOwner(')
assert dry_run_pos < owner_construct_pos
assert 'print("P13B_DRY_RUN=PASS")' in tool
assert 'print("HARDWARE_UART_OPENED=NO")' in tool
assert 'print("RF_TRANSMITTED=NO")' in tool
assert 'print("EXTERNAL_DECODE_REQUIRED=YES")' in tool
assert 'print("YWD1278_0B_P13B_INTERNAL_SINGLE_TX=PASS")' in tool

print("P13B_SINGLE_TX_CONTRACT=PASS")
print("ORIGINAL_P13B_ONE_SHOT_PRESERVED=PASS")
print("P12B_HISTORICAL_EVIDENCE_FROZEN=PASS")
print("P13B_FREQUENCY_HZ=145050000")
print("P13B_FRAME_VECTOR=PASS")
print("P13B_SELECTOR_COUNT=753")
print("P13B_PACKED_SELECTOR_BYTES=95")
print("P13B_EXPECTED_GENERATED_SAMPLES=12048")
print("MAX_TX_SUBMISSIONS=1")
print("AUTOMATIC_TX_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("FLASH_PATH=ABSENT")
print("GPIO_RESET_PATH=ABSENT")
print("OPTION_BYTE_PATH=ABSENT")
print("RF_TRANSMITTED_BY_CI=NO")
