"""Pure RSSI characterization helpers for YWD-1278 0C-P2.

This module analyzes already-collected raw ADF7021 RSSI magnitudes. It does not
own a modem, read hardware, classify production channel state, or connect to
CSMA/TX. 0C-P2 uses it only to characterize observed cluster separation before
a carrier threshold and hysteresis are selected in a later explicit gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import Iterable


@dataclass(frozen=True)
class RSSIClusterSeparation:
    low_count: int
    low_min: int
    low_median: float
    low_max: int
    high_count: int
    high_min: int
    high_median: float
    high_max: int
    gap: int
    midpoint: int


@dataclass(frozen=True)
class RSSIFrameCorrelation:
    sample_start: int
    sample_end: int
    count: int
    raw_min: int
    raw_median: float
    raw_max: int


def largest_cluster_gap(
    values: Iterable[int],
    *,
    min_low_count: int = 5,
    min_high_count: int = 20,
) -> RSSIClusterSeparation:
    """Return the largest observed integer gap that leaves useful data on both sides.

    ``midpoint`` is descriptive evidence only. Calling this function does not
    select or enable a carrier threshold.
    """

    samples = sorted(int(value) for value in values)
    if len(samples) < min_low_count + min_high_count:
        raise ValueError("too few RSSI samples for the requested cluster sizes")
    if min_low_count < 1 or min_high_count < 1:
        raise ValueError("minimum cluster sizes must be positive")

    best: tuple[int, int, int] | None = None
    # i is the first index of the upper cluster. Equal adjacent values do not
    # form a gap and therefore cannot be selected.
    for i in range(min_low_count, len(samples) - min_high_count + 1):
        lower = samples[i - 1]
        upper = samples[i]
        gap = upper - lower
        if gap <= 0:
            continue
        candidate = (gap, -lower, i)
        if best is None or candidate > best:
            best = candidate

    if best is None:
        raise ValueError("no separating RSSI gap was observed")

    _, _, split = best
    low = samples[:split]
    high = samples[split:]
    low_max = low[-1]
    high_min = high[0]
    gap = high_min - low_max
    return RSSIClusterSeparation(
        low_count=len(low),
        low_min=low[0],
        low_median=statistics.median(low),
        low_max=low_max,
        high_count=len(high),
        high_min=high_min,
        high_median=statistics.median(high),
        high_max=high[-1],
        gap=gap,
        midpoint=(low_max + high_min) // 2,
    )


def correlate_rssi_window(
    rssi_samples: Iterable[tuple[int, int]],
    *,
    sample_start: int,
    sample_end: int,
    padding_samples: int = 0,
) -> RSSIFrameCorrelation:
    """Summarize RSSI samples whose capture positions overlap one frame window."""

    if sample_start < 0 or sample_end < sample_start:
        raise ValueError("invalid frame sample interval")
    if padding_samples < 0:
        raise ValueError("padding_samples must be non-negative")

    lo = max(0, sample_start - padding_samples)
    hi = sample_end + padding_samples
    selected = [
        int(raw)
        for position, raw in rssi_samples
        if lo <= int(position) <= hi
    ]
    if not selected:
        raise ValueError("no RSSI samples overlap the requested frame interval")

    return RSSIFrameCorrelation(
        sample_start=sample_start,
        sample_end=sample_end,
        count=len(selected),
        raw_min=min(selected),
        raw_median=statistics.median(selected),
        raw_max=max(selected),
    )
