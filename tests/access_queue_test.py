#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.tx.access_queue import (  # noqa: E402
    AccessQueueFrameRejected,
    AccessQueueFull,
    AccessRequestState,
    BoundedChannelAccessQueue,
)
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402


def frame(text: str) -> bytes:
    return build_ui_frame(
        source=Address("KJ6YWD", 10),
        destination=Address("YWD127"),
        info=text.encode("ascii"),
        include_fcs=True,
    )


class Bytes:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> int:
        if not self.values:
            raise AssertionError("random source exhausted")
        self.calls += 1
        return self.values.pop(0)


class Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[bytes, float | None]] = []
        self.fail = fail

    def submit_frame(self, frame_with_fcs: bytes, *, timeout: float | None = None) -> object:
        self.calls.append((bytes(frame_with_fcs), timeout))
        if self.fail:
            raise RuntimeError("synthetic downstream rejection")
        return {"accepted": len(self.calls)}


# Basic path: no downstream call until qualified detector + full P1 slot reaches
# READY. READY dispatches exactly once and later observations cannot resubmit it.
rec = Recorder()
queue = BoundedChannelAccessQueue(rec)
first_frame = frame("P4A FIRST")
receipt = queue.enqueue(first_frame, now=0.0)
assert receipt.request_id == 1
assert receipt.deadline_at == 30.0
assert rec.calls == []

obs = queue.observe_rssi(now=0.00, raw_magnitude=106)
assert obs.request_state is AccessRequestState.ACCESS
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.RECENT_RX
assert obs.access.csma.state is CSMAState.WAIT_CLEAR
assert rec.calls == []

obs = queue.observe_rssi(now=0.26, raw_magnitude=106)
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.CLEAR
assert obs.access.csma.state is CSMAState.WAIT_SLOT
assert rec.calls == []

rng = Bytes([0])
obs = queue.observe_rssi(now=0.37, raw_magnitude=106, random_byte_source=rng)
assert obs.request_state is AccessRequestState.DISPATCHED
assert obs.access is not None and obs.access.csma.state is CSMAState.READY
assert obs.downstream_called is True
assert obs.downstream_result == {"accepted": 1}
assert obs.downstream_error == ""
assert rec.calls == [(first_frame, 1.5)]
assert rng.calls == 1
assert queue.snapshot.queue_depth == 0
assert queue.snapshot.dispatched_requests == 1

obs = queue.observe_rssi(now=0.50, raw_magnitude=48, random_byte_source=Bytes([0]))
assert obs.request_id is None
assert obs.downstream_called is False
assert len(rec.calls) == 1

# Live busy semantics survive the queue layer: after initial CLEAR starts a slot,
# BUSY cancels it, RECENT_RX remains WAIT_CLEAR, and only a later full fresh slot
# can dispatch. No random byte is consumed by busy/recent-RX observations.
second_frame = frame("P4A BUSY RESET")
queue.enqueue(second_frame, now=1.0)
rng = Bytes([0])
queue.observe_rssi(now=1.00, raw_magnitude=106, random_byte_source=rng)
queue.observe_rssi(now=1.26, raw_magnitude=106, random_byte_source=rng)
obs = queue.observe_rssi(now=1.30, raw_magnitude=48, random_byte_source=rng)
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.BUSY
assert obs.access.csma.state is CSMAState.WAIT_CLEAR
assert obs.access.csma.next_slot_at is None
assert rng.calls == 0
assert len(rec.calls) == 1

for now in (1.35, 1.40, 1.45, 1.50, 1.55):
    obs = queue.observe_rssi(now=now, raw_magnitude=106, random_byte_source=rng)
    assert obs.access is not None
    assert obs.access.detector.state is ChannelBusyState.RECENT_RX
    assert obs.access.csma.state is CSMAState.WAIT_CLEAR
    assert obs.downstream_called is False
assert rng.calls == 0

obs = queue.observe_rssi(now=1.61, raw_magnitude=106, random_byte_source=rng)
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.CLEAR
assert obs.access.csma.state is CSMAState.WAIT_SLOT
assert obs.downstream_called is False

obs = queue.observe_rssi(now=1.72, raw_magnitude=106, random_byte_source=rng)
assert obs.request_state is AccessRequestState.DISPATCHED
assert obs.access is not None and obs.access.csma.state is CSMAState.READY
assert rng.calls == 1
assert [call[0] for call in rec.calls] == [first_frame, second_frame]

# Invalid FCS is rejected before queueing or channel access.
bad = bytearray(frame("P4A BAD FCS"))
bad[-1] ^= 0x01
try:
    queue.enqueue(bytes(bad), now=2.0)
except AccessQueueFrameRejected:
    pass
else:
    raise AssertionError("invalid FCS entered access queue")
assert queue.snapshot.invalid_rejections == 1
assert queue.snapshot.queue_depth == 0

# Capacity is strict and includes the current head request.
small = BoundedChannelAccessQueue(Recorder(), queue_capacity=2)
small.enqueue(frame("Q1"), now=3.0)
small.enqueue(frame("Q2"), now=3.0)
try:
    small.enqueue(frame("Q3"), now=3.0)
except AccessQueueFull:
    pass
else:
    raise AssertionError("bounded access queue accepted over-capacity request")
assert small.snapshot.queue_depth == 2
assert small.snapshot.queue_full_rejections == 1

# Total request lifetime starts at enqueue. A stale queued request is terminal
# without calling downstream and without being granted a fresh 30 seconds.
time_rec = Recorder()
timeq = BoundedChannelAccessQueue(time_rec, request_timeout_seconds=0.50)
timeq.enqueue(frame("TIME HEAD"), now=10.0)
timeq.observe_rssi(now=10.00, raw_magnitude=106)
timeq.observe_rssi(now=10.26, raw_magnitude=106)
obs = timeq.observe_rssi(now=10.37, raw_magnitude=106, random_byte_source=Bytes([0]))
assert obs.request_state is AccessRequestState.DISPATCHED
assert len(time_rec.calls) == 1

timeq.enqueue(frame("TIME STALE"), now=10.37)
obs = timeq.observe_rssi(now=10.88, raw_magnitude=106, random_byte_source=Bytes([0]))
assert obs.request_state is AccessRequestState.TIMED_OUT
assert obs.downstream_called is False
assert len(time_rec.calls) == 1
assert timeq.snapshot.timed_out_requests == 1

# Downstream failure is terminal and is never retried by later RSSI samples.
fail_rec = Recorder(fail=True)
failq = BoundedChannelAccessQueue(fail_rec)
fail_frame = frame("P4A DOWNSTREAM FAIL")
failq.enqueue(fail_frame, now=20.0)
failq.observe_rssi(now=20.00, raw_magnitude=106)
failq.observe_rssi(now=20.26, raw_magnitude=106)
obs = failq.observe_rssi(now=20.37, raw_magnitude=106, random_byte_source=Bytes([0]))
assert obs.request_state is AccessRequestState.DOWNSTREAM_FAILED
assert obs.downstream_called is True
assert "synthetic downstream rejection" in obs.downstream_error
assert len(fail_rec.calls) == 1
assert failq.snapshot.downstream_failures == 1
assert failq.snapshot.queue_depth == 0
failq.observe_rssi(now=20.50, raw_magnitude=106, random_byte_source=Bytes([0]))
assert len(fail_rec.calls) == 1

# Two queued requests cannot consume the same observation. After request one is
# dispatched, request two remains queued until the caller supplies fresh RSSI.
multi_rec = Recorder()
multi = BoundedChannelAccessQueue(multi_rec, queue_capacity=2)
a = multi.enqueue(frame("MULTI A"), now=30.0)
b = multi.enqueue(frame("MULTI B"), now=30.0)
assert (a.request_id, b.request_id) == (1, 2)
multi.observe_rssi(now=30.00, raw_magnitude=106)
multi.observe_rssi(now=30.26, raw_magnitude=106)
obs = multi.observe_rssi(now=30.37, raw_magnitude=106, random_byte_source=Bytes([0]))
assert obs.request_id == 1 and obs.request_state is AccessRequestState.DISPATCHED
assert multi.snapshot.queue_depth == 1
assert multi.snapshot.active_request_id is None
assert len(multi_rec.calls) == 1
obs = multi.observe_rssi(now=30.38, raw_magnitude=106)
assert obs.request_id == 2
assert obs.request_state is AccessRequestState.ACCESS
assert obs.access is not None and obs.access.csma.state is CSMAState.WAIT_CLEAR
assert len(multi_rec.calls) == 1

print("P4A_BOUNDED_ACCESS_QUEUE=PASS")
print("VALID_FCS_BEFORE_QUEUE=PASS")
print("QUEUE_CAPACITY=BOUNDED")
print("TOTAL_REQUEST_LIFETIME=BOUNDED_FROM_ENQUEUE")
print("BUSY_CANCELS_ACCESS=PASS")
print("RECENT_RX_REMAINS_BUSY_FOR_ACCESS=PASS")
print("READY_DISPATCH_EXACTLY_ONCE=PASS")
print("DOWNSTREAM_FAILURE_RETRY=NO")
print("SAME_OBSERVATION_MULTI_DISPATCH=NO")
print("REAL_TX_BROKER_USED=NO")
print("MODEM_UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
