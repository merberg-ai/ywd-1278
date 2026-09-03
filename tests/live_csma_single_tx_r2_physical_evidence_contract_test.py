#!/usr/bin/env python3
"""Lock the exact 0C-P4d-R2 physical CSMA/TX evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p4d-r2-live-csma-single-tx-physical-evidence.json"
STAGE = ROOT / "firmware" / "qualification" / "0c-p4d-r2-live-csma-single-tx.json"


def main() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    stage = json.loads(STAGE.read_text(encoding="utf-8"))

    assert evidence["phase"] == "0C-P4d-R2"
    assert evidence["status"] == "physically-qualified"
    assert evidence["staging_checkpoint_sha"] == "b1bed159afe981496c54c0f7182a7e89149ede65"
    assert evidence["frequency_hz"] == stage["frequency_hz"] == 145_050_000
    assert evidence["rf_power"] == stage["rf_power"] == 200
    assert evidence["runtime_identity"] == stage["expected_identity"]

    for key in (
        "source",
        "destination",
        "information_text",
        "frame_bytes",
        "selector_count",
        "packed_selector_bytes",
        "packed_selector_sha256",
        "expected_generated_samples",
    ):
        assert evidence[key] == stage[key], key

    # R2 staging intentionally stores only the minimum locked-vector fields;
    # preserve the additional exact physical-evidence hashes independently.
    assert evidence["frame_hex"] == (
        "b2ae88688840e096946cb2ae887503f05957442d31323738205034442043534d"
        "412056455249465920312f310a32"
    )
    assert evidence["frame_sha256"] == "2f700a4dd7675473a183e119b711ed44c1f0a1ed3a70505523c63af8d42d6655"

    assert evidence["rssi_samples"] == 242
    assert evidence["packed_rx_bytes_drained"] == 28_942
    assert evidence["rx_status_checks"] == 46
    assert evidence["fifo_dropped_bytes"] == 0
    assert evidence["pre_busy_defer_trials"] == 81
    assert evidence["post_busy_persist_trials"] == 2

    assert evidence["busy_elapsed_seconds"] == 10.700
    assert evidence["clear_elapsed_seconds"] == 11.800
    assert evidence["defer_elapsed_seconds"] == 11.900
    assert evidence["dispatch_elapsed_seconds"] == 12.050
    assert evidence["clear_to_defer_seconds"] >= 0.100
    assert evidence["defer_to_dispatch_seconds"] >= 0.100

    for key in (
        "rx_start_before_rssi",
        "live_busy_observed",
        "busy_forced_csma_wait_clear",
        "recent_rx_busy_for_access",
        "post_busy_clear_observed",
        "post_busy_full_slot",
        "post_busy_persist_255_defer",
        "post_busy_persist_0_dispatch",
        "rx_stop_after_ready_before_broker",
        "rx_inactive_before_tx_tones",
        "diagnostic_counters_reset_on_accept",
        "single_modem_owner",
        "uart_released",
    ):
        assert evidence[key] is True, key

    assert stage["rx_start_required_before_rssi"] is True
    assert stage["rx_fifo_drain_while_sampling"] is True
    assert stage["half_duplex_handoff"] == "RX_STOP_AFTER_READY_BEFORE_BROKER_SUBMIT"
    assert stage["rx_must_be_inactive_before_tx_tones"] is True

    assert evidence["transmit_submissions"] == stage["maximum_transmit_submissions"] == 1
    assert evidence["diagnostic_counter_semantics"] == "reset-on-accepted-burst"
    # These are absolute reset-on-accept diagnostics, not lifetime deltas.
    assert evidence["rf_keyups_before"] == 1
    assert evidence["rf_generated_samples_before"] == 12_048
    assert evidence["rf_keyups_completed_burst_absolute"] == 1
    assert evidence["rf_generated_samples_completed_burst_absolute"] == 12_048
    assert evidence["duplicate_dispatch"] is False

    assert evidence["kiss_tx_connected"] is stage["kiss_tx_connected"] is False
    assert evidence["product_tx_enabled"] is stage["product_tx_enabled"] is False
    assert evidence["automatic_tx_retry"] is stage["automatic_tx_retry"] is False
    assert evidence["flash_written"] is False
    assert evidence["gpio_accessed"] is False
    assert evidence["option_bytes_written"] is False
    assert evidence["rf_transmitted"] is True
    assert evidence["rf_transmission_count"] == 1

    external = evidence["external_decode"]
    assert stage["external_decode_required"] is True
    assert external["required"] is True
    assert external["observed"] is True
    assert external["count"] == 1
    assert external["decoded_source"] == evidence["source"]
    assert external["decoded_destination"] == evidence["destination"]
    assert external["decoded_information_text"] == evidence["information_text"]
    assert external["exact_expected_frame_observed"] is True

    r1 = evidence["r1_pre_tx_failure"]
    assert r1["preserved"] is True
    assert r1["checkpoint_sha"] == stage["r1_staged_checkpoint_sha"]
    assert r1["checkpoint_sha"] == "d2ff131b989ad4fe81baa8a86067383e98e66c73"
    assert r1["transmit_submissions"] == 0
    assert r1["rf_transmitted"] is False

    print("P4D_R2_PHYSICAL_EVIDENCE_CONTRACT=PASS")


if __name__ == "__main__":
    main()
