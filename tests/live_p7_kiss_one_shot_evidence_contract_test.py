#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p7-live-kiss-one-shot-physical-evidence.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert d["schema"] == 1
    assert d["phase"] == "0C-P7-live"
    assert d["status"] == "physically-qualified"
    assert d["staged_checkpoint"] == "checkpoint/0c-p7-live-kiss-one-shot-staged-green"
    assert d["staged_checkpoint_sha"] == "788702f5b66999c3ba1e69f29b23f8c7eae28484"
    assert d["host_checkpoint_sha"] == "3df9a46f0851876e55c078ab41504584304bef38"
    assert d["frequency_hz"] == 145050000
    assert d["rf_power"] == 200

    assert d["live_harness_result"] == "YWD1278_0C_P7_LIVE_KISS_ONE_SHOT_EXECUTION=PASS"
    assert d["kiss_data_messages_received"] == 1
    assert d["kiss_data_admitted"] == 1
    assert d["kiss_data_without_fcs"] is True
    assert d["tnc_appended_fcs_exactly_once"] is True
    assert d["parameter_generation_captured"] == 3
    assert d["captured_txdelay"] == 30
    assert d["captured_persist"] == 63
    assert d["captured_slottime"] == 10
    assert d["kiss_listener_closed_before_access"] is True

    assert d["pre_tx_fresh_non_p7_rx_decode"] is True
    assert d["live_busy_observed"] is True
    assert d["persist_255_defer"] is True
    assert d["persist_0_dispatch"] is True
    assert d["clear_to_defer_seconds"] == 0.150
    assert d["defer_to_dispatch_seconds"] == 0.100
    assert d["rx_stop_tx_rx_restart"] is True

    assert d["tx_submissions"] == 1
    assert d["tx_frame_bytes"] == 52
    assert d["tx_selector_count"] == 801
    assert d["tx_packed_selector_bytes"] == 101
    assert d["tx_packed_selector_sha256"] == "82fff4f7b03ae787fb16d6d14cc9a59e81e7b3f751a3e4be1e090320d26b2b7f"
    assert d["rf_keyups_completed_burst_absolute"] == 1
    assert d["rf_generated_samples_completed_burst_absolute"] == 12816

    assert d["inbound_fcs_valid_frames_total"] == 3
    assert d["qualifying_non_p7_inbound_frames"] == 2
    assert d["p7_qualification_echoes_ignored"] == 1
    assert d["final_post_tx_non_p7_fcs_valid_rx"] is True
    final = d["final_post_tx_inbound_frame"]
    assert final == {
        "source": "KJ6YWD-5",
        "destination": "KE6CHO-5",
        "frame_type": "RR",
        "frame_bytes": 17,
        "information_text": "",
    }

    assert d["rssi_samples"] == 188
    assert d["packed_rx_bytes_drained"] == 86271
    assert d["rx_status_checks"] == 137
    assert d["peak_fifo_available_bytes"] == 130
    assert d["fifo_dropped_bytes"] == 0
    assert d["ax25_path"] == ["YWDNOD"]
    assert d["ywdnod_repeat_gate"] == "deferred-non-blocking"

    ext = d["external_receiver"]
    assert ext["required_exact_decodes"] == 1
    assert ext["observed_exact_decodes"] == 1
    assert ext["direct_decode_gate_satisfied"] is True
    assert ext["observation"]["local_time"] == "14:21:18"
    assert ext["observation"]["line"] == "KJ6YWD-10>YWD7,YWDNOD:YWD-1278 P7 KISS VERIFY 1/1"

    assert d["single_modem_owner"] is True
    assert d["uart_released"] is True
    assert d["duplicate_dispatch"] is False
    assert d["automatic_tx_retry"] is False
    assert d["persistent_kiss_tx_enabled"] is False
    assert d["product_tx_enabled"] is False
    assert d["flash_written"] is False
    assert d["gpio_accessed"] is False
    assert d["option_bytes_written"] is False
    assert d["rf_transmitted"] == "exactly-one-kiss-originated-burst"
    assert d["external_decode_gate_satisfied"] is True
    assert d["qualification_complete"] is True

    print("P7_LIVE_PHYSICAL_EVIDENCE_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
