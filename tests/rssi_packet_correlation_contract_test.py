#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "qualify_rssi_packet_correlation.py"
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p2-rssi-live-physical-evidence.json"
text = TOOL.read_text(encoding="utf-8")
evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

assert evidence["status"] == "physically-qualified-telemetry-only"
assert evidence["firmware"]["artifact_size_bytes"] == 59892
assert evidence["firmware"]["artifact_sha256"] == "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
assert evidence["firmware"]["programmed_readback_sha256"] == evidence["firmware"]["artifact_sha256"]
assert evidence["firmware"]["left_installed"] is True
assert evidence["receive_observation"]["rssi_sample_count"] == 401
assert evidence["receive_observation"]["fifo_dropped_bytes"] == 0
assert evidence["observed_bimodality"]["low_cluster_max"] == 73
assert evidence["observed_bimodality"]["normal_cluster_min"] == 95
assert evidence["safety"]["rf_transmitted"] is False
assert evidence["safety"]["carrier_threshold_selected"] is False
assert evidence["safety"]["hysteresis_selected"] is False

# The next live gate is fixed to the exact installed AX25R4 target state and
# only correlates read-only RSSI telemetry with already-qualified RX decoding.
# Polarity must be proven directly against an independent outside-frame sample
# population before the descriptive guard gap is computed.
for required in (
    'DEVICE = "/dev/ttyAMA0"',
    "FREQUENCY_HZ = 145_050_000",
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1",
    "StreamingBell202Decoder",
    "ModemOwner(",
    "owner.rx_start",
    "owner.rx_read",
    "owner.rx_rssi",
    "owner.rx_status",
    "owner.rf_status",
    "owner.rf_diagnostics",
    "guard_gap_above_signal",
    "correlate_rssi_window",
    "rssi_values_outside_windows",
    "OUTSIDE_FRAME_GUARD_SAMPLES",
    "MIN_OUTSIDE_SAMPLES = 20",
    "MIN_POLARITY_MARGIN = 12",
    "outside_median - packet_worst_median",
    "signal_reference_max",
    "MIN_SEPARATING_GAP = 12",
    "RSSI_POLARITY=LOWER_RAW_IS_STRONGER_RF",
    "PACKET_WORST_MEDIAN=",
    "OUTSIDE_FRAME_MEDIAN=",
    "POLARITY_MARGIN=",
    "POLARITY_PROOF_INDEPENDENT_OF_GUARD_GAP=PASS",
    "PACKET_SIGNAL_REFERENCE_MAX=",
    "OBSERVED_BUSY_SIDE_MAX=",
    "OBSERVED_UPPER_SIDE_MIN=",
    "CARRIER_THRESHOLD_SELECTED=NO",
    "HYSTERESIS_SELECTED=NO",
    "CSMA_INTEGRATION=NO",
    "RF_TRANSMITTED=NO",
):
    assert required in text, required

# Prevent the earlier circular test from reappearing: polarity may not be
# inferred merely by comparing packet medians with a midpoint derived from the
# same packet-referenced gap.
assert "low_correlations" not in text
assert "corr.raw_median < separation.midpoint" not in text

# No operator knobs can redirect this characterization to arbitrary hardware or
# RF settings; there is intentionally no argparse surface at all.
for forbidden in (
    "argparse",
    "--device",
    "--frequency",
    "--identity",
    "--threshold",
    "--hysteresis",
    "TXModemOwner",
    "TXBroker",
    "transmit_selector_burst",
    "rf_tx_tones_request",
    "YWD_RF_TX_TONES",
    "PersistentCSMA",
    "KISSServer",
    "stm32flash",
    "pinctrl",
    "raspi-gpio",
):
    assert forbidden not in text, forbidden

print("P2_PACKET_CORRELATED_RSSI_CONTRACT=PASS")
print("EXACT_AX25R4_INSTALLED_BOUNDARY=YES")
print("FCS_VALID_PACKET_CORRELATION_REQUIRED=YES")
print("INDEPENDENT_OUTSIDE_FRAME_POLARITY_PROOF=YES")
print("PACKET_REFERENCED_GUARD_GAP_REQUIRED=YES")
print("MIN_POLARITY_MARGIN=12")
print("MIN_SEPARATING_GAP=12")
print("CARRIER_THRESHOLD_SELECTED=NO")
print("HYSTERESIS_SELECTED=NO")
print("TX_PATH=ABSENT")
