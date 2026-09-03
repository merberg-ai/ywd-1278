#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "tx" / "channel_busy.py"
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p2-rssi-packet-correlation-physical-evidence.json"
DOC = ROOT / "docs" / "qualifications" / "0c-p2-packet-correlated-rssi-qualified-2026-09-02.md"

text = MODULE.read_text(encoding="utf-8")
evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
doc = DOC.read_text(encoding="utf-8")

assert evidence["status"] == "physically-qualified-correlation"
assert evidence["firmware"]["artifact_sha256"] == "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
assert evidence["receive_observation"]["frequency_hz"] == 145050000
assert evidence["receive_observation"]["valid_ax25_frames"] == 2
assert evidence["receive_observation"]["correlated_frame_windows"] == 2
assert evidence["receive_observation"]["fifo_dropped_bytes"] == 0
assert evidence["polarity_proof"]["packet_worst_median_raw"] == 48
assert evidence["polarity_proof"]["outside_frame_median_raw"] == 106
assert evidence["polarity_proof"]["observed_margin_raw_counts"] == 58
assert evidence["polarity_proof"]["result"] == "pass"
assert evidence["polarity_proof"]["polarity"] == "lower-raw-is-stronger-rf"
assert evidence["polarity_proof"]["independent_of_guard_gap_selection"] is True
assert evidence["guard_gap_observation"]["observed_busy_or_transition_side_max"] == 70
assert evidence["guard_gap_observation"]["observed_upper_population_min"] == 97
assert evidence["guard_gap_observation"]["descriptive_midpoint"] == 83
assert evidence["guard_gap_observation"]["carrier_threshold_selected"] is False
assert evidence["guard_gap_observation"]["hysteresis_selected"] is False
assert evidence["safety"]["rf_keyups_before"] == 0
assert evidence["safety"]["rf_keyups_after"] == 0
assert evidence["safety"]["rf_tx_generated_samples_before"] == 0
assert evidence["safety"]["rf_tx_generated_samples_after"] == 0
assert evidence["safety"]["rf_transmitted"] is False
assert evidence["safety"]["csma_integration"] is False

# Both exact physical frame occurrences stay locked.
assert evidence["frames"][0]["sample_start"] == 99924
assert evidence["frames"][0]["sample_end"] == 108636
assert evidence["frames"][0]["information_text"] == "73 from redding"
assert evidence["frames"][0]["rssi_raw_median"] == 48
assert evidence["frames"][1]["sample_start"] == 149339
assert evidence["frames"][1]["sample_end"] == 157403
assert evidence["frames"][1]["information_text"] == "hello test"
assert evidence["frames"][1]["rssi_raw_median"] == 48

# The host policy must remain conservatively inside the physically empty gap.
for required in (
    "BUSY_ASSERT_RAW_MAX = 83",
    "CLEAR_RELEASE_RAW_MIN = 90",
    "RECENT_RX_HOLD_SECONDS = 0.250",
    "PHYSICAL_BUSY_SIDE_MAX = 70",
    "PHYSICAL_UPPER_SIDE_MIN = 97",
    "PHYSICAL_DESCRIPTIVE_MIDPOINT = 83",
    "PHYSICAL_RSSI_POLL_SECONDS = 0.050",
    "ChannelBusyState.UNKNOWN",
    "ChannelBusyState.RECENT_RX",
    "channel_busy=self._state is not ChannelBusyState.CLEAR",
):
    assert required in text, required

# Host-only means genuinely host-only: no I/O, modem, service, KISS, TX broker,
# CSMA state machine, sleep, RNG imports/calls, GPIO, or firmware calls are allowed.
for forbidden in (
    "ywd1278.modem",
    "ywd1278.kiss",
    "PersistentCSMA",
    "TXBroker",
    "serial",
    "socket",
    "subprocess",
    "threading",
    "time.sleep",
    "import random",
    "from random",
    "random.",
    "pinctrl",
    "raspi-gpio",
    "stm32flash",
    "transmit_selector_burst",
    "rf_tx_tones_request",
):
    assert forbidden not in text, forbidden

assert "58" in doc
assert "70..97" in doc
assert "no firmware flash occurred during this run" in doc.lower()

print("CHANNEL_BUSY_ARCHITECTURE_CONTRACT=PASS")
print("PHYSICAL_PACKET_CORRELATION_LOCKED=YES")
print("THRESHOLDS_INSIDE_PHYSICAL_GAP=YES")
print("RECENT_RX_HOLD_FIVE_RSSI_POLLS=YES")
print("HOST_ONLY=YES")
print("MODEM_INTEGRATION=NO")
print("CSMA_INTEGRATION=NO")
print("TX_INTEGRATION=NO")
