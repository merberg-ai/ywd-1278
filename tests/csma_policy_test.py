#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.csma import (  # noqa: E402
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_PERSIST,
    DEFAULT_SLOT_TIME_10MS,
    CSMAParameters,
    CSMAState,
    PersistentCSMA,
)


def expect_value_error(fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def close(actual: float, expected: float) -> None:
    assert abs(actual - expected) < 1e-9, (actual, expected)


# Frozen classic defaults.
defaults = CSMAParameters()
assert defaults.persist == 63
assert defaults.slot_time_10ms == 10
close(defaults.slot_seconds, 0.1)
close(defaults.max_wait_seconds, 30.0)
close(defaults.persistence_probability, 0.25)
assert DEFAULT_PERSIST == 63
assert DEFAULT_SLOT_TIME_10MS == 10
assert DEFAULT_MAX_WAIT_SECONDS == 30.0

# Parameter validation is fail closed.
for bad in (-1, 256):
    expect_value_error(lambda bad=bad: CSMAParameters(persist=bad))
for bad in (0, 256):
    expect_value_error(lambda bad=bad: CSMAParameters(slot_time_10ms=bad))
for bad in (0.0, -0.1):
    expect_value_error(lambda bad=bad: CSMAParameters(max_wait_seconds=bad))
expect_value_error(lambda: PersistentCSMA(started_at=-0.001))

# A clear channel must remain clear for one complete slot before a persistence
# trial is allowed.
p = PersistentCSMA(started_at=10.0)
d = p.observe(now=10.05, channel_busy=False)
assert d.state is CSMAState.WAIT_SLOT
assert d.ready is False
close(d.next_slot_at, 10.1)
expect_value_error(lambda: p.observe(now=10.06, channel_busy=False, random_byte=0))

# At the first due slot the default PERSIST=63 accepts random byte 63 and rejects 64.
p = PersistentCSMA(started_at=20.0)
d = p.observe(now=20.1, channel_busy=False, random_byte=63)
assert d.state is CSMAState.READY
assert d.ready is True
assert d.persistence_trials == 1
assert d.random_byte == 63

p = PersistentCSMA(started_at=30.0)
d = p.observe(now=30.1, channel_busy=False, random_byte=64)
assert d.state is CSMAState.WAIT_SLOT
assert d.ready is False
assert d.persistence_trials == 1
close(d.next_slot_at, 30.2)
assert d.reason == "persistence trial deferred; waiting one more slot"
d = p.observe(now=d.next_slot_at, channel_busy=False, random_byte=0)
assert d.state is CSMAState.READY
assert d.persistence_trials == 2

# Busy observations never consume randomness and restart the complete-slot wait.
p = PersistentCSMA(started_at=40.0)
d = p.observe(now=40.09, channel_busy=True)
assert d.state is CSMAState.WAIT_SLOT
assert d.busy_observations == 1
close(d.next_slot_at, 40.19)
expect_value_error(lambda: p.observe(now=40.10, channel_busy=True, random_byte=0))
d = p.observe(now=40.18, channel_busy=False)
assert d.ready is False
close(d.next_slot_at, 40.19)
d = p.observe(now=d.next_slot_at, channel_busy=False, random_byte=1)
assert d.ready is True

# A busy observation after a failed persistence trial restarts the slot timer
# from the busy observation, not from the previous persistence slot.
p = PersistentCSMA(started_at=50.0)
d = p.observe(now=50.1, channel_busy=False, random_byte=255)
assert d.ready is False
close(d.next_slot_at, 50.2)
d = p.observe(now=50.15, channel_busy=True)
close(d.next_slot_at, 50.25)
assert d.busy_observations == 1
assert d.persistence_trials == 1

# PERSIST boundaries are exact over the whole byte domain: 255 always passes;
# 0 passes exactly one possible random byte (zero).
passes_255 = 0
passes_0 = 0
for random_byte in range(256):
    p255 = PersistentCSMA(
        started_at=0.0,
        parameters=CSMAParameters(persist=255, slot_time_10ms=1),
    )
    if p255.observe(now=0.01, channel_busy=False, random_byte=random_byte).ready:
        passes_255 += 1

    p0 = PersistentCSMA(
        started_at=0.0,
        parameters=CSMAParameters(persist=0, slot_time_10ms=1),
    )
    if p0.observe(now=0.01, channel_busy=False, random_byte=random_byte).ready:
        passes_0 += 1
assert passes_255 == 256
assert passes_0 == 1

# Timeout is bounded and fail-closed even with an otherwise clear channel.
p = PersistentCSMA(
    started_at=100.0,
    parameters=CSMAParameters(persist=255, slot_time_10ms=10, max_wait_seconds=0.25),
)
d = p.observe(now=100.1, channel_busy=False, random_byte=255)
assert d.ready is True

p = PersistentCSMA(
    started_at=200.0,
    parameters=CSMAParameters(persist=0, slot_time_10ms=10, max_wait_seconds=0.25),
)
d = p.observe(now=200.1, channel_busy=False, random_byte=255)
assert d.ready is False
d = p.observe(now=d.next_slot_at, channel_busy=False, random_byte=255)
assert d.ready is False
d = p.observe(now=200.25, channel_busy=False)
assert d.state is CSMAState.TIMED_OUT
assert d.timed_out is True
assert d.persistence_trials == 2

# Terminal state is sticky and cannot reopen access or consume another random draw.
d2 = p.observe(now=201.0, channel_busy=False)
assert d2 == d
expect_value_error(lambda: p.observe(now=201.1, channel_busy=False, random_byte=0))

ready = PersistentCSMA(started_at=300.0)
d = ready.observe(now=300.1, channel_busy=False, random_byte=0)
assert d.ready is True
assert ready.observe(now=301.0, channel_busy=True) == d
expect_value_error(lambda: ready.observe(now=301.1, channel_busy=False, random_byte=0))

# Time within one attempt must be monotonic.
p = PersistentCSMA(started_at=400.0)
p.observe(now=400.05, channel_busy=False)
expect_value_error(lambda: p.observe(now=400.04, channel_busy=False))

print("CSMA_POLICY_REGRESSION=PASS")
print("CSMA_DEFAULT_PERSIST=63")
print("CSMA_DEFAULT_PERSIST_PROBABILITY=0.25")
print("CSMA_DEFAULT_SLOTTIME_10MS=10")
print("CSMA_DEFAULT_SLOT_SECONDS=0.1")
print("CSMA_DEFAULT_MAX_WAIT_SECONDS=30.0")
print("BUSY_RESTARTS_SLOT=PASS")
print("PERSIST_BOUNDARIES=PASS")
print("BOUNDED_TIMEOUT=PASS")
print("TERMINAL_STATE_STICKY=PASS")
print("RF_TRANSMITTED=NO")
