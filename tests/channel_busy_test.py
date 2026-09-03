#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.channel_busy import (
    BUSY_ASSERT_RAW_MAX,
    CLEAR_RELEASE_RAW_MIN,
    PHYSICAL_BUSY_SIDE_MAX,
    PHYSICAL_DESCRIPTIVE_MIDPOINT,
    PHYSICAL_RSSI_POLL_SECONDS,
    PHYSICAL_UPPER_SIDE_MIN,
    RECENT_RX_HOLD_SECONDS,
    ChannelBusyState,
    RSSIChannelBusyDetector,
)

assert PHYSICAL_BUSY_SIDE_MAX == 70
assert PHYSICAL_UPPER_SIDE_MIN == 97
assert PHYSICAL_DESCRIPTIVE_MIDPOINT == 83
assert PHYSICAL_RSSI_POLL_SECONDS == 0.050
assert BUSY_ASSERT_RAW_MAX == 83
assert CLEAR_RELEASE_RAW_MIN == 90
assert RECENT_RX_HOLD_SECONDS == 0.250
assert PHYSICAL_BUSY_SIDE_MAX < BUSY_ASSERT_RAW_MAX
assert BUSY_ASSERT_RAW_MAX < CLEAR_RELEASE_RAW_MIN
assert CLEAR_RELEASE_RAW_MIN < PHYSICAL_UPPER_SIDE_MIN
assert RECENT_RX_HOLD_SECONDS == 5 * PHYSICAL_RSSI_POLL_SECONDS

# Startup is fail-closed. One apparently-clear sample can only begin the hold.
d = RSSIChannelBusyDetector(started_at=10.0)
assert d.state is ChannelBusyState.UNKNOWN
first = d.observe(now=10.0, raw_magnitude=106)
assert first.state is ChannelBusyState.RECENT_RX
assert first.channel_busy is True
assert first.recent_rx is True
assert first.clear_candidate_since == 10.0

# Clear is not reached before the full hold, even at the physical outside median.
assert d.observe(now=10.249, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
clear = d.observe(now=10.250, raw_magnitude=106)
assert clear.state is ChannelBusyState.CLEAR
assert clear.channel_busy is False
assert clear.recent_rx is False

# Once clear, the hysteresis band does not chatter the state busy.
for raw in range(BUSY_ASSERT_RAW_MAX + 1, CLEAR_RELEASE_RAW_MIN):
    held = d.observe(now=10.300 + raw / 10000.0, raw_magnitude=raw)
    assert held.state is ChannelBusyState.CLEAR, raw
    assert held.channel_busy is False

# Every value at/below assert immediately forces BUSY, including the threshold.
for raw in (83, 82, 70, 48, 0):
    x = RSSIChannelBusyDetector()
    result = x.observe(now=0.0, raw_magnitude=raw)
    assert result.state is ChannelBusyState.BUSY, raw
    assert result.channel_busy is True
    assert result.last_busy_at == 0.0

# Physical packet values are unambiguously busy.
for raw in range(47, PHYSICAL_BUSY_SIDE_MAX + 1):
    x = RSSIChannelBusyDetector()
    assert x.observe(now=0.0, raw_magnitude=raw).state is ChannelBusyState.BUSY

# A busy detector requires continuously release-side RSSI for the whole hold.
d = RSSIChannelBusyDetector()
assert d.observe(now=0.000, raw_magnitude=48).state is ChannelBusyState.BUSY
assert d.observe(now=0.050, raw_magnitude=97).state is ChannelBusyState.RECENT_RX
assert d.observe(now=0.200, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=0.299, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=0.300, raw_magnitude=106).state is ChannelBusyState.CLEAR

# An ambiguous hysteresis-band sample while not clear cancels release qualification.
d = RSSIChannelBusyDetector()
assert d.observe(now=0.000, raw_magnitude=48).state is ChannelBusyState.BUSY
assert d.observe(now=0.050, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
mid = d.observe(now=0.200, raw_magnitude=86)
assert mid.state is ChannelBusyState.RECENT_RX
assert mid.channel_busy is True
assert mid.clear_candidate_since is None
restart = d.observe(now=0.250, raw_magnitude=106)
assert restart.state is ChannelBusyState.RECENT_RX
assert restart.clear_candidate_since == 0.250
assert d.observe(now=0.499, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=0.500, raw_magnitude=106).state is ChannelBusyState.CLEAR

# A new busy observation immediately cancels a pending release and restarts history.
d = RSSIChannelBusyDetector()
assert d.observe(now=1.000, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=1.100, raw_magnitude=48).state is ChannelBusyState.BUSY
assert d.observe(now=1.150, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=1.399, raw_magnitude=106).state is ChannelBusyState.RECENT_RX
assert d.observe(now=1.400, raw_magnitude=106).state is ChannelBusyState.CLEAR

# Exact boundary semantics are locked.
x = RSSIChannelBusyDetector()
assert x.observe(now=0.0, raw_magnitude=BUSY_ASSERT_RAW_MAX).state is ChannelBusyState.BUSY
assert x.observe(now=0.1, raw_magnitude=BUSY_ASSERT_RAW_MAX + 1).state is ChannelBusyState.BUSY
assert x.observe(now=0.2, raw_magnitude=CLEAR_RELEASE_RAW_MIN - 1).state is ChannelBusyState.BUSY
assert x.observe(now=0.3, raw_magnitude=CLEAR_RELEASE_RAW_MIN).state is ChannelBusyState.RECENT_RX
assert x.observe(now=0.55, raw_magnitude=CLEAR_RELEASE_RAW_MIN).state is ChannelBusyState.CLEAR

# Invalid time and raw values fail closed as programmer errors.
x = RSSIChannelBusyDetector(started_at=1.0)
for raw in (-1, 256):
    try:
        x.observe(now=1.0, raw_magnitude=raw)
    except ValueError:
        pass
    else:
        raise AssertionError(f"invalid raw RSSI accepted: {raw}")

x.observe(now=2.0, raw_magnitude=106)
try:
    x.observe(now=1.9, raw_magnitude=106)
except ValueError:
    pass
else:
    raise AssertionError("non-monotonic detector time was accepted")

print("CHANNEL_BUSY_DETECTOR_REGRESSION=PASS")
print("PHYSICAL_BUSY_SIDE_MAX=70")
print("BUSY_ASSERT_RAW_MAX=83")
print("CLEAR_RELEASE_RAW_MIN=90")
print("PHYSICAL_UPPER_SIDE_MIN=97")
print("HYSTERESIS_BAND=84..89")
print("RECENT_RX_HOLD_SECONDS=0.250")
print("STARTUP_FAIL_CLOSED=YES")
print("MODEM_INTEGRATION=NO")
print("CSMA_INTEGRATION=NO")
print("TX_INTEGRATION=NO")
