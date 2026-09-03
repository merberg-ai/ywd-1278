#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.channel_access import (  # noqa: E402
    ChannelAccessRandomnessRequired,
    ShadowChannelAccessAttempt,
)
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402


class Bytes:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> int:
        if not self.values:
            raise AssertionError("random byte source exhausted")
        self.calls += 1
        return self.values.pop(0)


# Startup fails closed through the complete 250 ms detector release hold.
source = Bytes([255, 255, 0])
attempt = ShadowChannelAccessAttempt(started_at=0.0)

for now in (0.00, 0.05, 0.10, 0.15, 0.20):
    obs = attempt.observe_rssi(now=now, raw_magnitude=106, random_byte_source=source)
    assert obs.detector.state is ChannelBusyState.RECENT_RX
    assert obs.detector.channel_busy is True
    assert obs.csma.state is CSMAState.WAIT_CLEAR
    assert obs.random_byte is None
assert source.calls == 0

# Use 0.26 rather than relying on a binary-float exact 0.25 boundary.
obs = attempt.observe_rssi(now=0.26, raw_magnitude=106, random_byte_source=source)
assert obs.detector.state is ChannelBusyState.CLEAR
assert obs.detector.channel_busy is False
assert obs.csma.state is CSMAState.WAIT_SLOT
assert obs.csma.next_slot_at == 0.36
assert obs.random_byte is None
assert source.calls == 0

# Before the full 100 ms P1 slot, the RNG must not be touched.
obs = attempt.observe_rssi(now=0.35, raw_magnitude=106, random_byte_source=source)
assert obs.csma.state is CSMAState.WAIT_SLOT
assert obs.random_byte is None
assert source.calls == 0

# First due slot consumes exactly one caller byte and defers on 255.
obs = attempt.observe_rssi(now=0.36, raw_magnitude=106, random_byte_source=source)
assert obs.detector.state is ChannelBusyState.CLEAR
assert obs.csma.state is CSMAState.WAIT_SLOT
assert obs.csma.persistence_trials == 1
assert obs.random_byte == 255
assert obs.csma.next_slot_at == 0.46
assert source.calls == 1

# A real busy-side sample cancels that in-progress slot immediately. No random
# byte is consumed even though the prior slot deadline is reached later.
obs = attempt.observe_rssi(now=0.40, raw_magnitude=48, random_byte_source=source)
assert obs.detector.state is ChannelBusyState.BUSY
assert obs.detector.channel_busy is True
assert obs.csma.state is CSMAState.WAIT_CLEAR
assert obs.csma.next_slot_at is None
assert obs.csma.busy_observations == 1
assert obs.random_byte is None
assert source.calls == 1

# Detector recent-RX hold remains busy-for-access, so P1 cannot begin a slot.
for now in (0.45, 0.50, 0.55, 0.60, 0.65):
    obs = attempt.observe_rssi(now=now, raw_magnitude=106, random_byte_source=source)
    assert obs.detector.state is ChannelBusyState.RECENT_RX
    assert obs.detector.channel_busy is True
    assert obs.csma.state is CSMAState.WAIT_CLEAR
    assert obs.csma.next_slot_at is None
    assert obs.random_byte is None
assert source.calls == 1

# Once the 250 ms release hold completes, P1 starts a brand-new full 100 ms slot.
obs = attempt.observe_rssi(now=0.71, raw_magnitude=106, random_byte_source=source)
assert obs.detector.state is ChannelBusyState.CLEAR
assert obs.csma.state is CSMAState.WAIT_SLOT
assert obs.csma.next_slot_at == 0.81
assert obs.random_byte is None

# First post-busy trial defers, proving PERSIST semantics remain unchanged.
obs = attempt.observe_rssi(now=0.82, raw_magnitude=106, random_byte_source=source)
assert obs.csma.state is CSMAState.WAIT_SLOT
assert obs.csma.persistence_trials == 2
assert obs.random_byte == 255
assert obs.csma.next_slot_at == 0.92
assert source.calls == 2

# Second post-busy trial passes on byte zero. READY is shadow-only; no TX exists.
obs = attempt.observe_rssi(now=0.93, raw_magnitude=106, random_byte_source=source)
assert obs.csma.state is CSMAState.READY
assert obs.csma.ready is True
assert obs.csma.persistence_trials == 3
assert obs.random_byte == 0
assert source.calls == 3

# P1 terminal semantics stay sticky even if later RSSI becomes busy. The
# surrounding scheduler will eventually create a fresh attempt per TX request;
# this 0C-P3 object represents exactly one already-qualified P1 attempt.
obs2 = attempt.observe_rssi(now=1.00, raw_magnitude=48, random_byte_source=source)
assert obs2.detector.state is ChannelBusyState.BUSY
assert obs2.csma.state is CSMAState.READY
assert obs2.random_byte is None
assert source.calls == 3

# Missing randomness when a clear persistence slot is due fails visibly and
# does not silently invent an RNG draw.
missing = ShadowChannelAccessAttempt(started_at=10.0)
for now in (10.00, 10.05, 10.10, 10.15, 10.20, 10.26):
    missing.observe_rssi(now=now, raw_magnitude=106)
try:
    missing.observe_rssi(now=10.36, raw_magnitude=106)
except ChannelAccessRandomnessRequired:
    pass
else:
    raise AssertionError("due persistence slot accepted missing randomness")
assert missing.csma.decision.state is CSMAState.WAIT_SLOT
assert missing.csma.decision.persistence_trials == 0

print("CHANNEL_ACCESS_INTEGRATION_TEST=PASS")
print("DETECTOR_RECENT_RX_FEEDS_P1_BUSY=PASS")
print("BUSY_CANCELS_P1_CLEAR_SLOT=PASS")
print("POST_BUSY_FULL_SLOT_REQUIRED=PASS")
print("PERSIST_DEFER_BYTE=255")
print("PERSIST_PASS_BYTE=0")
print("HIDDEN_RANDOMNESS=NO")
print("TX_PATH=ABSENT")
