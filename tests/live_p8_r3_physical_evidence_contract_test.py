#!/usr/bin/env python3
"""Contract for the successful 0C-P8 R3 physical qualification evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-physical-evidence.json"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-sustained-kiss-tnc.json"


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert evidence["schema"] == 1
    assert evidence["phase"] == "0C-P8-R3-live"
    assert evidence["status"] == "physically-qualified"
    assert evidence["qualification_complete"] is True
    assert evidence["rerun_same_stage_permitted"] is False
    assert evidence["execution_head_sha"] == "b301e9098aedf64e4eb9adf746b93a8f7a7482ac"
    assert evidence["base_checkpoint_sha"] == "e8d104b2c6a295219e34733d2541f89ee90318f3"
    assert evidence["frequency_hz"] == 145050000
    assert evidence["rf_power"] == 200
    assert evidence["r3_accepted_tx"] == 3
    assert evidence["r3_transmitted_fixed_bursts"] == 3
    assert evidence["external_direct_decode_required"] == 3
    assert evidence["external_direct_decode_observed"] == 3
    assert evidence["external_decode_result"] == "pass"
    assert [x["packet"] for x in evidence["external_decoder_observations"]] == [
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 1/3",
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 2/3",
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 3/3",
    ]
    assert [x["local_time"] for x in evidence["external_decoder_observations"]] == [
        "15:25:21", "15:25:31", "15:25:48"
    ]
    assert evidence["external_decoder_screenshot_sha256"] == (
        "139c7c3be655677fd245653f50f35ca3d943598872f4e9e1587b21c22744b901"
    )
    assert evidence["external_decoder_screenshot_dimensions"] == [1017, 261]

    assert evidence["kiss_tcp_clients"] == 2
    assert evidence["kiss_client_reconnect"] == "pass"
    assert evidence["kiss_data_admitted"] == 3
    assert evidence["tx_submissions"] == 3
    assert evidence["complete_rx_tx_rx_cycles"] == 3
    assert evidence["initial_rx_starts"] == 1
    assert evidence["post_tx_rx_restarts"] == 3
    assert evidence["total_rx_starts"] == 4
    assert evidence["total_rx_stops"] == 3
    assert evidence["post_tx_decoder_resets"] == 3
    assert evidence["inbound_non_p8_fcs_valid_frames"] == 4
    assert evidence["rssi_samples"] == 172
    assert evidence["packed_rx_bytes_drained"] == 112514
    assert evidence["rx_read_transactions"] == 593
    assert evidence["rx_status_checks"] == 115
    assert evidence["fifo_dropped_bytes"] == 0
    assert evidence["rx_fifo_backlog_priority"] == "pass"
    assert evidence["serialized_queue_clock_sampling"] == "pass"
    assert evidence["single_modem_owner"] == "pass"
    assert evidence["uart_released"] is True
    assert evidence["duplicate_dispatch"] is False
    assert evidence["automatic_tx_retry"] is False

    cycles = evidence["cycles"]
    assert len(cycles) == 3
    assert [x["generated_samples"] for x in cycles] == [12960, 16784, 12944]
    assert [x["clear_to_defer_seconds"] for x in cycles] == [0.314, 6.881, 15.424]
    assert [x["defer_to_dispatch_seconds"] for x in cycles] == [0.223, 0.175, 0.228]
    assert cycles[1]["qualification_echo_fresh_non_p8"] is False
    assert cycles[2]["qualification_echo_fresh_non_p8"] is False

    semantic = evidence["semantic_self_echo_filter"]
    assert semantic["result"] == "pass"
    assert semantic["address_ch_flags_ignored_for_identity"] is True
    assert semantic["cycle2_echo_suppressed"] is True
    assert semantic["cycle3_echo_suppressed"] is True
    assert semantic["final_echo_suppressed"] is True
    assert semantic["genuine_nonqualification_frames_required"] == 4
    assert semantic["genuine_nonqualification_frames_observed"] == 4

    final = evidence["final_queue_empty_proof"]
    assert final["tx_queue_empty"] is True
    assert final["qualification_echo_counted_as_non_qualification"] is False
    assert final["fresh_non_qualification_frame"] == "KJ6YWD>JIM"
    assert final["fcs_valid_rx"] == "pass"
    assert final["kiss_delivery"] == "pass"

    for key in (
        "three_external_direct_decodes",
        "three_fixed_rf_bursts",
        "three_rx_stop_tx_rx_restart_cycles",
        "kiss_two_client_reconnect",
        "fifo_drops_zero",
        "fresh_non_qualification_rx_gate",
        "semantic_self_echo_exclusion",
        "final_queue_empty_non_qualification_rx_proof",
    ):
        assert evidence["subproofs"][key] == "pass", key

    assert evidence["live_harness_result"] == "YWD1278_0C_P8_LIVE_SUSTAINED_KISS_EXECUTION=PASS"
    assert evidence["wrapper_result"] == "P8_R3_WRAPPER_RESULT=PASS"
    assert evidence["external_decode_gate_satisfied"] is True

    assert manifest["status"] == "physically-qualified"
    assert manifest["runnable"] is False
    assert manifest["qualification_complete"] is True
    assert manifest["execution_head_sha"] == evidence["execution_head_sha"]
    assert manifest["physical_evidence"] == "firmware/qualification/0c-p8-r3-live-physical-evidence.json"
    assert manifest["r3_accepted_tx"] == 3
    assert manifest["r3_external_direct_decodes"] == 3
    assert manifest["r3_rerun_permitted"] is False

    print("P8_R3_PHYSICAL_EVIDENCE_CONTRACT=PASS")
    print("R3_EXTERNAL_DIRECT_DECODE=3_OF_3")
    print("R3_COMPLETE_RX_TX_RX_CYCLES=3")
    print("R3_SEMANTIC_SELF_ECHO_EXCLUSION=PASS")
    print("R3_GENUINE_NONQUAL_RX_FRAMES=4")
    print("R3_FINAL_QUEUE_EMPTY_RX_KISS=PASS")
    print("R3_RERUN=FORBIDDEN")
    print("P8_PHYSICAL_QUALIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
