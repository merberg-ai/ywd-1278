#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.rssi_analysis import (
    cluster_gaps,
    correlate_rssi_window,
    guard_gap_above_signal,
    rssi_values_outside_windows,
)

# Reproduce the physically observed P2 separation shape without making the
# production classifier depend on a single capture. The one 73-count sample is
# deliberately retained because it was observed at an RF-event edge.
observed_shape = (
    [47] + [48] * 40 + [49] * 5 + [73]
    + [95, 96, 97] + [98] * 6 + [99] * 8 + [100] * 13
    + [101] * 18 + [102] * 25 + [103] * 31 + [104] * 30
    + [105] * 30 + [106] * 29 + [107] * 24 + [108] * 19
    + [109] * 18 + [110] * 15 + [111] * 20 + [112] * 16
    + [113] * 15 + [114] * 8 + [115] * 8 + [116] * 8
    + [117] * 5 + [118] * 5 + [119] * 3 + [120] * 2
    + [121] * 3 + [122]
)

gaps = cluster_gaps(observed_shape, min_low_count=5, min_high_count=20)
assert any(item.low_max == 49 and item.high_min == 73 and item.gap == 24 for item in gaps)
assert any(item.low_max == 73 and item.high_min == 95 and item.gap == 22 for item in gaps)

# Packet-correlated signal evidence lives in the 47..49 core. The guard-gap
# rule intentionally chooses the highest still-large gap above that signal
# reference, keeping transition value 73 on the signal/busy side.
sep = guard_gap_above_signal(
    observed_shape,
    signal_reference_max=49,
    min_gap=12,
    min_low_count=5,
    min_high_count=20,
)
assert sep.low_max == 73
assert sep.high_min == 95
assert sep.gap == 22
assert sep.midpoint == 84
assert sep.low_median == 48
assert sep.high_median >= 100

# A packet window and an independently selected outside-frame population are
# separate pieces of evidence. The polarity assertion is based on their direct
# median difference, not on a gap chosen from the packet values themselves.
samples = [
    (0, 106),
    (1000, 104),
    (2000, 48),
    (3000, 49),
    (4000, 48),
    (5000, 47),
    (6000, 105),
    (7000, 108),
]
corr = correlate_rssi_window(
    samples,
    sample_start=2000,
    sample_end=5000,
)
assert corr.count == 4
assert corr.raw_min == 47
assert corr.raw_median == 48
assert corr.raw_max == 49
outside = rssi_values_outside_windows(samples, [(2000, 5000)])
assert outside == (106, 104, 105, 108)
assert statistics.median(outside) - corr.raw_median == 57.5

outside_with_guard = rssi_values_outside_windows(
    samples,
    [(2500, 4500)],
    padding_samples=500,
)
assert outside_with_guard == (106, 104, 105, 108)

# Guard malformed or underdetermined characterization inputs.
for bad in ([], [100] * 24):
    try:
        cluster_gaps(bad, min_low_count=5, min_high_count=20)
    except ValueError:
        pass
    else:
        raise AssertionError("underdetermined RSSI data did not fail closed")

try:
    guard_gap_above_signal(
        [47] * 10 + [48] * 10 + [50] * 30,
        signal_reference_max=48,
        min_gap=12,
    )
except ValueError:
    pass
else:
    raise AssertionError("weakly separated RSSI data did not fail closed")

try:
    correlate_rssi_window(samples, sample_start=6000, sample_end=1000)
except ValueError:
    pass
else:
    raise AssertionError("invalid frame interval did not fail closed")

try:
    rssi_values_outside_windows(samples, [(0, 7000)], padding_samples=0)
except ValueError:
    pass
else:
    raise AssertionError("empty outside-frame RSSI population did not fail closed")

print("RSSI_ANALYSIS_REGRESSION=PASS")
print("INDEPENDENT_OUTSIDE_FRAME_POPULATION=PASS")
print("PHYSICAL_SIGNAL_CORE_GAP=49_TO_73")
print("PHYSICAL_GUARD_GAP=73_TO_95")
print("PHYSICAL_GUARD_MIDPOINT_DESCRIPTIVE_ONLY=84")
print("CARRIER_THRESHOLD_SELECTED=NO")
print("CSMA_INTEGRATION=NO")
