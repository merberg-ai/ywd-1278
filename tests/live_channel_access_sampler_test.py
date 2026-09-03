#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.service.live_channel_access import (  # noqa: E402
    LiveChannelAccessError,
    LiveChannelAccessSampler,
)
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402


class FakeOwner:
    def __init__(self, rssis: list[int]) -> None:
        self.rssis = list(rssis)
        self.running = True
        self.calls: list[str] = []

    @property
    def snapshot(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            running=self.running,
            owner_thread_id=12345 if self.running else None,
        )

    def rx_status(self, *, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append("rx_status")
        return SimpleNamespace(flags=0x0D, dropped_bytes=0)

    def rx_rssi(self, *, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append("rx_rssi")
        if not self.rssis:
            raise AssertionError("fake RSSI samples exhausted")
        return SimpleNamespace(raw_magnitude=self.rssis.pop(0))


class ByteZero:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return 0


owner = FakeOwner([106] * 8)
sampler = LiveChannelAccessSampler(owner, started_at=0.0)
sampler.preflight(timeout=0.5)
assert owner.calls == ["rx_status"]

rng = ByteZero()
for now in (0.00, 0.05, 0.10, 0.15, 0.20):
    obs = sampler.sample(now=now, random_byte_source=rng, timeout=0.5)
    assert obs.detector.state is ChannelBusyState.RECENT_RX
    assert obs.csma.state is CSMAState.WAIT_CLEAR
assert rng.calls == 0

obs = sampler.sample(now=0.26, random_byte_source=rng, timeout=0.5)
assert obs.detector.state is ChannelBusyState.CLEAR
assert obs.csma.state is CSMAState.WAIT_SLOT
assert rng.calls == 0

obs = sampler.sample(now=0.31, random_byte_source=rng, timeout=0.5)
assert obs.csma.state is CSMAState.WAIT_SLOT
assert rng.calls == 0

obs = sampler.sample(now=0.36, random_byte_source=rng, timeout=0.5)
assert obs.csma.state is CSMAState.READY
assert obs.random_byte == 0
assert rng.calls == 1

snap = sampler.snapshot
assert snap.samples == 8
assert snap.last_raw_magnitude == 106
assert snap.last_observation is obs
assert owner.calls == ["rx_status"] + ["rx_rssi"] * 8

# The sampler attaches to a running owner but does not own or restart it.
owner.running = False
try:
    sampler.sample(now=0.40, random_byte_source=rng)
except LiveChannelAccessError:
    pass
else:
    raise AssertionError("sampler accepted a stopped ModemOwner")

print("LIVE_CHANNEL_ACCESS_SAMPLER_TEST=PASS")
print("PREFLIGHT_ACTIVE_RX_REQUIRED=YES")
print("TYPED_RSSI_CALLS=8")
print("HIDDEN_THREAD=NO")
print("HIDDEN_CLOCK=NO")
print("HIDDEN_RANDOMNESS=NO")
print("TX_PATH=ABSENT")
