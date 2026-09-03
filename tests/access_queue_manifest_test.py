#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads(
    (ROOT / "firmware" / "qualification" / "0c-p4a-bounded-access-queue.json").read_text(
        encoding="utf-8"
    )
)

assert data["schema"] == 1
assert data["phase"] == "0C-P4a"
assert data["status"] == "host-qualified"
assert data["base_checkpoint"] == "checkpoint/0c-p3-live-shadow-channel-access-qualified"
assert data["base_checkpoint_sha"] == "6303f3e49ec4ace2df3855b14f0c488aa3638926"
assert data["queue_capacity"] == 4
assert data["total_request_lifetime_seconds"] == 30.0
assert data["downstream_timeout_seconds"] == 1.5
assert data["valid_fcs_required_before_queue"] is True
assert data["queue_wait_consumes_request_lifetime"] is True
assert data["fresh_access_attempt_per_head_request"] is True
assert data["one_rssi_observation_advances_one_head_request"] is True
assert data["fresh_observation_required_for_next_request"] is True
assert data["ready_dispatch_exactly_once"] is True
assert data["automatic_downstream_retry"] is False
assert data["p1"] == {"persist": 63, "slot_time_10ms": 10, "maximum_wait_seconds": 30.0}
assert data["p2"] == {
    "busy_assert_raw_max": 83,
    "clear_release_raw_min": 90,
    "recent_rx_hold_seconds": 0.25,
}
assert data["initial_ci"] == {
    "workflow": "framework-ci",
    "run_number": 346,
    "run_id": 33705580315,
    "head_sha": "f9f87c28df3b21ac2d8402d6f20646554036f835",
    "conclusion": "success",
}
for key in (
    "concrete_tx_broker_connected",
    "tx_modem_owner_connected",
    "kiss_tx_connected",
    "product_tx_enabled",
    "hardware_access",
    "rf_transmitted",
    "flash_written",
    "option_bytes_written",
):
    assert data[key] is False, key

print("P4A_QUALIFICATION_MANIFEST=PASS")
print("STATUS=HOST_QUALIFIED")
print("BASE_CHECKPOINT=0C-P3_QUALIFIED")
print("INITIAL_CI_RUN=346_SUCCESS")
print("CONCRETE_TX_BROKER_CONNECTED=NO")
print("KISS_TX_CONNECTED=NO")
print("HARDWARE_ACCESS=NO")
print("RF_TRANSMITTED=NO")
