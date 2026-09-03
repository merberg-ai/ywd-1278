#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.rssi_analysis import correlate_rssi_window, largest_cluster_gap

# Reproduce the physically observed P2 separation shape without making the
# production classifier depend on a single capture.
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

sep = largest_cluster_gap(observed_shape, min_low_count=5, min_high_count=20)
assert sep.low_max == 73
assert sep.high_min == 95
assert sep.gap == 22
assert sep.midpoint == 84
assert sep.low_median == 48
assert sep.high_median >= 100

# A packet window whose RSSI measurements are in the low cluster must summarize
# independently of the global separation calculation.
samples = [
    (0, 106),
    (1000, 104),
    (2000, 48),
    (3000, 49),
    (4000, 48),
    (5000, 47),
    (6000, 105),
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

# Guard malformed or underdetermined characterization inputs.
for bad in ([], [100] * 24):
    try:
        largest_cluster_gap(bad, min_low_count=5, min_high_count=20)
    except ValueError:
        pass
    else:
        raise AssertionError("underdetermined RSSI data did not fail closed")

try:
    correlate_rssi_window(samples, sample_start=6000, sample_end=1000)
except ValueError:
    pass
else:
    raise AssertionError("invalid frame interval did not fail closed")

print("RSSI_ANALYSIS_REGRESSION=PASS")
print("PHYSICAL_SHAPE_GAP=22")
print("PHYSICAL_SHAPE_MIDPOINT_DESCRIPTIVE_ONLY=84")
print("CARRIER_THRESHOLD_SELECTED=NO")
print("CSMA_INTEGRATION=NO")
