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


def cluster_gaps(
    values: Iterable[int],
    *,
    min_low_count: int = 5,
    min_high_count: int = 20,
) -> tuple[RSSIClusterSeparation, ...]:
    """Return every observed positive gap with useful samples on both sides."""

    samples = sorted(int(value) for value in values)
    if len(samples) < min_low_count + min_high_count:
        raise ValueError("too few RSSI samples for the requested cluster sizes")
    if min_low_count < 1 or min_high_count < 1:
        raise ValueError("minimum cluster sizes must be positive")

    out: list[RSSIClusterSeparation] = []
    for split in range(min_low_count, len(samples) - min_high_count + 1):
        low_max = samples[split - 1]
        high_min = samples[split]
        gap = high_min - low_max
        if gap <= 0:
            continue
        low = samples[:split]
        high = samples[split:]
        out.append(
            RSSIClusterSeparation(
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
        )
    if not out:
        raise ValueError("no separating RSSI gap was observed")
    return tuple(out)


def guard_gap_above_signal(
    values: Iterable[int],
    *,
    signal_reference_max: int,
    min_gap: int,
    min_low_count: int = 5,
    min_high_count: int = 20,
) -> RSSIClusterSeparation:
    """Choose the highest well-separated gap that still contains signal evidence below it.

    Packet-correlated RSSI provides ``signal_reference_max``. Choosing the
    highest qualifying gap above that reference deliberately keeps any
    intermediate transition values on the signal/busy side rather than
    prematurely treating them as clear-channel evidence.

    The returned midpoint is descriptive only; this function does not select or
    enable a production carrier threshold.
    """

    if min_gap < 1:
        raise ValueError("min_gap must be positive")
    candidates = [
        item
        for item in cluster_gaps(
            values,
            min_low_count=min_low_count,
            min_high_count=min_high_count,
        )
        if item.low_max >= int(signal_reference_max) and item.gap >= min_gap
    ]
    if not candidates:
        raise ValueError("no qualifying guard gap exists above packet-correlated signal evidence")
    return max(candidates, key=lambda item: (item.low_max, item.gap))


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


def rssi_values_outside_windows(
    rssi_samples: Iterable[tuple[int, int]],
    windows: Iterable[tuple[int, int]],
    *,
    padding_samples: int = 0,
) -> tuple[int, ...]:
    """Return RSSI values outside every supplied capture-sample interval.

    This is used only as an independent comparison population for physical
    polarity characterization. Outside-frame samples are not automatically
    called "clear" because they may include undecoded RF activity.
    """

    if padding_samples < 0:
        raise ValueError("padding_samples must be non-negative")
    normalized: list[tuple[int, int]] = []
    for start, end in windows:
        start = int(start)
        end = int(end)
        if start < 0 or end < start:
            raise ValueError("invalid RSSI exclusion window")
        normalized.append((max(0, start - padding_samples), end + padding_samples))

    values = tuple(
        int(raw)
        for position, raw in rssi_samples
        if not any(lo <= int(position) <= hi for lo, hi in normalized)
    )
    if not values:
        raise ValueError("no RSSI samples remain outside the supplied windows")
    return values
