#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "firmware" / "qualification" / "0c-p4e-live-multicycle.json"
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p4e-live-multicycle-physical-evidence.json"

stage = json.loads(STAGE.read_text(encoding="utf-8"))
evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

assert evidence["schema"] == 1
assert evidence["phase"] == "0C-P4e-live"
assert evidence["status"] == "physically-qualified"
assert evidence["date"] == "2026-09-02"
assert evidence["staged_checkpoint"] == "checkpoint/0c-p4e-live-multicycle-staged-green"
assert evidence["staged_checkpoint_sha"] == "b19784a37f9500b14546a32410f6988be8a76c80"
assert evidence["host_checkpoint_sha"] == stage["base_checkpoint_sha"]
assert evidence["target_id"] == stage["target_id"]
assert evidence["device"] == stage["device"]
assert evidence["frequency_hz"] == stage["frequency_hz"] == 145050000
assert evidence["rf_power"] == stage["rf_power"] == 200
assert evidence["expected_identity"] == stage["expected_identity"]
assert evidence["runtime_identity_gate_passed"] is True
assert evidence["live_harness_result"] == "YWD1278_0C_P4E_LIVE_MULTICYCLE_EXECUTION=PASS"

assert evidence["complete_rx_tx_rx_cycles"] == stage["cycles"] == 3
assert evidence["initial_rx_starts"] == 1
assert evidence["post_tx_rx_restarts"] == 3
assert evidence["total_rx_starts"] == 4
assert evidence["tx_submissions"] == stage["maximum_transmit_submissions"] == 3
assert evidence["inbound_fcs_valid_frames"] == stage["required_total_inbound_decoded_frames"] == 4
assert evidence["pre_tx_fresh_decoded_triggers"] == stage["required_pre_tx_decoded_frames"] == 3
assert evidence["final_post_tx_fcs_valid_rx"] is True

assert evidence["rssi_samples"] == 647
assert evidence["packed_rx_bytes_drained"] == 100277
assert evidence["rx_status_checks"] == 157
assert evidence["peak_fifo_available_bytes"] == 122
assert evidence["fifo_dropped_bytes"] == stage["rx_fifo_dropped_bytes_required"] == 0

assert len(evidence["cycles"]) == 3
for index, cycle in enumerate(evidence["cycles"]):
    staged = stage["frames"][index]
    cycle_number = index + 1
    assert cycle["cycle"] == staged["cycle"] == cycle_number
    assert cycle["live_busy"] is True
    assert cycle["fresh_rx_decode"] is True
    assert cycle["persist_255_defer"] is True
    assert cycle["persist_0_dispatch"] is True
    assert cycle["rx_stop_tx_rx_restart"] is True
    assert cycle["clear_to_defer_seconds"] == 0.150
    assert cycle["defer_to_dispatch_seconds"] == 0.100
    assert cycle["outgoing_frame"] == (
        f"{stage['source']}>{stage['destination']}:" + staged["information_text"]
    )
    assert cycle["frame_bytes"] == staged["frame_bytes"] == 40
    assert cycle["selector_count"] == staged["selector_count"] == 705
    assert cycle["expected_generated_samples"] == staged["expected_generated_samples"] == 11280

cycle3 = evidence["cycles"][2]
assert cycle3["observed_completed_burst_keyups"] == 1
assert cycle3["observed_generated_samples"] == 11280

final_rx = evidence["final_post_tx_inbound_frame"]
assert final_rx == {
    "source": "KJ6YWD",
    "destination": "JIM",
    "digipeater_path": ["KRDG", "KBANN", "KJOHN", "KBULN", "WOODY"],
    "frame_type": "UI",
    "frame_bytes": 60,
    "information_text": "hellooo",
}

external = evidence["external_receiver"]
assert external["evidence_type"] == "operator-supplied-independent-receiver-screenshot"
assert external["required_exact_decodes"] == stage["required_external_tx_decodes"] == 3
assert external["observed_exact_decodes"] == 3
assert external["all_three_exact_outgoing_frames_observed"] is True
expected_external = [
    ("20:22:01", "KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 1/3"),
    ("20:22:16", "KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 2/3"),
    ("20:22:29", "KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 3/3"),
]
assert [(item["local_time"], item["line"]) for item in external["observations"]] == expected_external

assert evidence["single_modem_owner"] is True
assert evidence["uart_released"] is True
assert evidence["duplicate_dispatch"] is False
assert evidence["automatic_tx_retry"] is False
assert evidence["kiss_tx_connected"] is False
assert evidence["product_tx_enabled"] is False
assert evidence["flash_written"] is False
assert evidence["gpio_accessed"] is False
assert evidence["option_bytes_written"] is False
assert evidence["rf_transmitted"] == "exactly-three-fixed-bursts"
assert evidence["external_decode_gate_satisfied"] is True
assert evidence["qualification_complete"] is True

print("P4E_LIVE_PHYSICAL_EVIDENCE=PASS")
print("COMPLETE_RX_TX_RX_CYCLES=3")
print("TOTAL_RX_STARTS=4")
print("INBOUND_FCS_VALID_FRAMES=4")
print("EXTERNAL_TX_DECODES=3")
print("FIFO_DROPPED_BYTES=0")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
