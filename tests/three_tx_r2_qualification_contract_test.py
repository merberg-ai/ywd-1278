#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, verify_fcs  # noqa: E402
from ywd1278.modem import tx_config  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402

TARGETS = ROOT / "firmware" / "targets.json"
STAGE = ROOT / "firmware" / "qualification" / "p13b-r2-three-tx.json"
TOOL = ROOT / "tools" / "qualify_tx_sequence_r2.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
stage = json.loads(STAGE.read_text(encoding="utf-8"))
tool = TOOL.read_text(encoding="utf-8")
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

# R2 still starts from the frozen P12b physical boundary and does not claim
# qualification until an independent decoder confirms at least one exact R2 frame.
assert target["status"] == "0b-p12b-live-rf-kiss-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
assert target["packet_live_rf_kiss_qualification"]["receive_frequency_hz"] == 145050000

assert stage["phase"] == "0B-P13b-R2"
assert stage["status"] == "staged"
assert stage["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert stage["transmit_frequency_hz"] == 145050000
assert stage["rf_power"] == 200
assert stage["source"] == "KJ6YWD-10"
assert stage["destination"] == "YWD13B"
assert stage["pre_flags"] == 45
assert stage["post_flags"] == 3
assert stage["initial_tone"] == "MARK"
assert stage["samples_per_selector"] == 16
assert stage["inter_packet_pause_seconds"] == 5.0
assert stage["maximum_transmissions"] == 3
assert stage["retry_transmit_on_failure"] is False
assert stage["diagnostic_counter_semantics"] == "reset-on-accepted-burst"
assert stage["expected_keyups_per_completed_burst"] == 1
assert stage["requires_external_decode"] is True
assert stage["minimum_external_decodes_required"] == 1
assert stage["kiss_tx_connected"] is False
assert stage["product_tx_enabled"] is False
assert stage["flash_permitted"] is False
assert stage["gpio_reset_permitted"] is False
assert stage["option_bytes_permitted"] is False
assert stage["confirmation_token"] == "P13B-R2-145050-P200-VERIFY-3"
assert len(stage["frames"]) == 3

expected_infos = [
    "YWD-1278 P13B R2 VERIFY 1/3",
    "YWD-1278 P13B R2 VERIFY 2/3",
    "YWD-1278 P13B R2 VERIFY 3/3",
]
expected_hashes = [
    "3d255111c073a51d9369e8fc26aaa6d9a9e8882cf532e0e56246913aaf5ece50",
    "0a4064718049ac9b36d7e617805cc47daae11199fad08faa7f3621660104c678",
    "e0377d1ca3d05c696a02ae5a5671ffeb32cfde4ad5b7467e6ed3605aed889f9b",
]
expected_packed_hashes = [
    "d147b12a8a24147c18f6a50847f866396e1d3d0ecd3595aeaecf7d99d22b7813",
    "14dd8eaf62ac46cc49acc81d55299912c909db9dc54f77b26df795f95aaa64ad",
    "f0c58606e7fe11e4a0b3c86864280bfde23b04b5130fb8a86ddfd1116ec5379e",
]

for index, vector in enumerate(stage["frames"]):
    assert vector["sequence"] == index + 1
    assert vector["information_text"] == expected_infos[index]
    frame = build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD13B"),
        info=expected_infos[index].encode("ascii"),
        include_fcs=True,
    )
    assert verify_fcs(frame)
    assert len(frame) == 45
    assert frame.hex() == vector["frame_hex"]
    assert hashlib.sha256(frame).hexdigest() == expected_hashes[index]
    selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3, initial_tone=MARK)
    packed = pack_selectors(selectors)
    assert len(selectors) == 745
    assert len(packed) == 94
    assert hashlib.sha256(packed).hexdigest() == expected_packed_hashes[index]
    assert len(selectors) * 16 == 11920
    assert vector["expected_generated_samples"] == 11920

# Fixed RF setup reuses the previously independently decoded AX25-5B level.
assert tx_config.P13B_TX_FREQUENCY_HZ == 145050000
assert tx_config.P13B_TX_POWER == 200
assert not hasattr(ModemOwner, "apply_tx_qualification_profile")
assert hasattr(TXModemOwner, "apply_tx_qualification_profile")

# The R2 harness exposes no arbitrary tuning, power, payload, source, target,
# device, serializer timing, pause, or count knobs.
assert 'TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"' in tool
assert 'DEVICE = "/dev/ttyAMA0"' in tool
assert 'CONFIRMATION_TOKEN = "P13B-R2-145050-P200-VERIFY-3"' in tool
assert 'ap.add_argument("--transmit", action="store_true")' in tool
assert 'ap.add_argument("--confirm", default="")' in tool
for forbidden_arg in (
    "--target",
    "--device",
    "--frequency",
    "--power",
    "--source",
    "--destination",
    "--payload",
    "--count",
    "--pause",
    "--pre-flags",
    "--post-flags",
):
    assert forbidden_arg not in tool, forbidden_arg

assert "owner.apply_tx_qualification_profile(timeout=1.5)" in tool
assert "owner.set_rx_frequency(" not in tool
assert 'transmit_enabled=True' in tool
assert 'queue_capacity=1' in tool
assert tool.count("broker.submit_frame(") == 1
assert "Never retry a failed call" in tool
assert 'if index < 3:' in tool
assert 'time.sleep(stage["inter_packet_pause_seconds"])' in tool

# Most important R2 correction: firmware diagnostics are per accepted burst.
# The tool must check absolute completed-burst values and must not use the R1
# lifetime-delta model.
assert 'post_diag.keyups != stage["expected_keyups_per_completed_burst"]' in tool
assert 'post_diag.generated_samples != vector["expected_generated_samples"]' in tool
assert "counter_delta(" not in tool
assert "RESET_ON_ACCEPT_COUNTER_ACCOUNTING=PASS" in tool
assert "THREE_COMPLETED_KEYUPS=PASS" in tool
assert "THREE_EXACT_GENERATED_SAMPLE_COUNTS=PASS" in tool

# Product/KISS paths remain disconnected and dangerous escape hatches remain absent.
for forbidden in ("TXBroker", "TXModemOwner", "transmit_selector_burst", "RF_TX_TONES"):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden
for forbidden in (
    "rf_abort_request",
    "rf_exit_request",
    "stm32flash",
    "pinctrl",
    "0x1FFFF800",
    "0x1ffff800",
    ".transact(",
):
    assert forbidden not in tool, forbidden

# Dry-run must return before owner construction and therefore before UART open.
dry_pos = tool.index("if not args.transmit:")
owner_pos = tool.index("owner = TXModemOwner(")
assert dry_pos < owner_pos
assert 'print("P13B_R2_DRY_RUN=PASS")' in tool
assert 'print("HARDWARE_UART_OPENED=NO")' in tool
assert 'print("RF_TRANSMITTED=NO")' in tool

print("P13B_R2_THREE_TX_CONTRACT=PASS")
print("P12B_PHYSICAL_BOUNDARY_FROZEN=PASS")
print("P13B_R2_FREQUENCY_HZ=145050000")
print("P13B_R2_RF_POWER=200")
print("RESET_ON_ACCEPT_COUNTER_SEMANTICS=PASS")
print("R2_FIXED_FRAMES=3")
print("R2_SELECTORS_PER_FRAME=745")
print("R2_SAMPLES_PER_FRAME=11920")
print("R2_INTER_PACKET_PAUSE_SECONDS=5.0")
print("AUTOMATIC_TX_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
