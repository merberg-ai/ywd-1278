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

# The current target has advanced through 0C-P2. Historical P12a/P12b and P13b
# evidence must remain present and unchanged beneath the later channel-access result.
assert target["status"] == "0c-p2-channel-busy-detector-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
p12b = target["packet_live_rf_kiss_qualification"]
assert p12b["phase"] == "0B-P12b"
assert p12b["status"] == "qualified"
assert p12b["receive_frequency_hz"] == 145050000
assert p12b["rf_transmitted"] is False
p13b = target["packet_live_tx_qualification"]
assert p13b["phase"] == "0B-P13b"
assert p13b["status"] == "qualified"
assert p13b["qualification_attempt"] == "0B-P13b-R2"
assert p13b["transmit_frequency_hz"] == 145050000
assert p13b["rf_power"] == 200
assert p13b["transmit_submissions"] == 3
assert p13b["completed_bursts"] == 3
assert p13b["external_decodes_observed"] == 3
assert p13b["all_three_exact_external_frames_observed"] is True
assert p13b["uart_released"] is True
assert p13b["kiss_tx_connected"] is False
assert p13b["product_tx_enabled"] is False
assert p13b["flash_written"] is False
assert p13b["gpio_accessed"] is False
assert p13b["option_bytes_written"] is False
assert p13b["automatic_tx_retry"] is False
p2 = target["channel_busy_qualification"]
assert p2["status"] == "host-qualified"
assert p2["modem_integration"] is False
assert p2["csma_integration"] is False
assert p2["kiss_tx_connected"] is False

assert stage["phase"] == "0B-P13b-R2"
assert stage["status"] == "qualified"
assert stage["qualification_date"] == "2026-09-02"
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

# Lock the exact physical internal evidence from the successful R2 run.
internal = stage["observed_internal_evidence"]
assert internal["transmit_submissions"] == 3
assert internal["completed_bursts"] == 3
assert internal["packet_firmware_identity_verified"] is True
assert internal["qualified_rf_power_profile_verified"] is True
assert internal["reset_on_accept_counter_accounting_verified"] is True
assert internal["fixed_five_second_gaps_verified"] is True
assert len(internal["bursts"]) == 3
for index, burst in enumerate(internal["bursts"], start=1):
    assert burst == {
        "sequence": index,
        "keyups_absolute": 1,
        "generated_samples_absolute": 11920,
        "counters_reset_on_accept": True,
    }
assert internal["modem_uart_released"] is True
assert internal["kiss_tx_connected"] is False
assert internal["product_tx_enabled"] is False
assert internal["flash_written"] is False
assert internal["gpio_accessed"] is False
assert internal["option_bytes_written"] is False
assert internal["automatic_tx_retry"] is False

# Lock the independent over-air decoder evidence. Qualification required one
# exact R2 frame; the receiver decoded all three exact frames in sequence.
external = stage["observed_external_decode_evidence"]
assert external["decodes_observed"] == 3
assert external["minimum_required"] == 1
assert external["all_three_exact_frames_observed"] is True
assert external["raw_decoder_lines"] == [
    "15:50:47 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 1/3",
    "15:50:53 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 2/3",
    "15:50:59 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 3/3",
]
assert external["normalized_frames"] == [
    "KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 1/3",
    "KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 2/3",
    "KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 3/3",
]

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

# Firmware diagnostics are per accepted burst. The tool checks absolute
# completed-burst values and never uses the invalid R1 lifetime-delta model.
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

# Dry-run returns before owner construction and therefore before UART open.
dry_pos = tool.index("if not args.transmit:")
owner_pos = tool.index("owner = TXModemOwner(")
assert dry_pos < owner_pos
assert 'print("P13B_R2_DRY_RUN=PASS")' in tool
assert 'print("HARDWARE_UART_OPENED=NO")' in tool
assert 'print("RF_TRANSMITTED=NO")' in tool

print("P13B_R2_THREE_TX_CONTRACT=PASS")
print("P13B_PHYSICAL_QUALIFICATION=PASS")
print("P12B_HISTORICAL_EVIDENCE_FROZEN=PASS")
print("P2_CURRENT_TARGET_BOUNDARY=QUALIFIED")
print("P13B_R2_FREQUENCY_HZ=145050000")
print("P13B_R2_RF_POWER=200")
print("RESET_ON_ACCEPT_COUNTER_SEMANTICS=PASS")
print("R2_FIXED_FRAMES=3")
print("R2_SELECTORS_PER_FRAME=745")
print("R2_SAMPLES_PER_FRAME=11920")
print("R2_INTER_PACKET_PAUSE_SECONDS=5.0")
print("R2_EXTERNAL_DECODES=3")
print("R2_ALL_EXACT_EXTERNAL_FRAMES=PASS")
print("AUTOMATIC_TX_RETRY=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
