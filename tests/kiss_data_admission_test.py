#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, verify_fcs  # noqa: E402
from ywd1278.kiss.control import TNCSessionState  # noqa: E402
from ywd1278.kiss.framing import KISSMessage, PERSIST, SLOTTIME, TXDELAY  # noqa: E402
from ywd1278.kiss.tx_path import (  # noqa: E402
    KISSDataAdmissionQueue,
    KISSDataFrameRejected,
    KISSDataQueueFull,
    KISSDataRequestState,
)
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402


def kiss_body(text: str) -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD7"),
        path=[Address.parse("YWDNOD")],
        info=text.encode("ascii"),
        include_fcs=False,
    )


class Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[bytes, object, float | None]] = []
        self.fail = fail

    def submit_frame(self, frame_with_fcs, context, *, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append((bytes(frame_with_fcs), context, timeout))
        if self.fail:
            raise RuntimeError("synthetic P7 downstream failure")
        return {"accepted": len(self.calls), "generation": context.parameters.generation}


class Bytes:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> int:
        if not self.values:
            raise AssertionError("random source exhausted")
        self.calls += 1
        return self.values.pop(0)


session = TNCSessionState()
# Generation 1/2/3 is the context that DATA will capture.
assert session.apply(KISSMessage(0, TXDELAY, bytes([50]))).updated
assert session.apply(KISSMessage(0, PERSIST, bytes([200]))).updated
assert session.apply(KISSMessage(0, SLOTTIME, bytes([20]))).updated
captured = session.capture_tx_context()
assert captured.parameters.generation == 3
assert captured.parameters.txdelay == 50
assert captured.parameters.persist == 200
assert captured.parameters.slottime == 20
assert captured.txdelay_profile.pre_flags == 75

rec = Recorder()
queue = KISSDataAdmissionQueue(rec)
body = kiss_body("YWD-1278 P7 CONTEXT FREEZE")
receipt = queue.enqueue(body, captured, now=0.0)
assert receipt.request_id == 1
assert receipt.frame_bytes_with_fcs == len(body) + 2
assert receipt.parameter_generation == 3
assert (receipt.txdelay, receipt.persist, receipt.slottime) == (50, 200, 20)
assert rec.calls == []

# Mutate the live session after admission.  The queued request must not change.
assert session.apply(KISSMessage(0, TXDELAY, bytes([30]))).updated
assert session.apply(KISSMessage(0, PERSIST, bytes([0]))).updated
assert session.apply(KISSMessage(0, SLOTTIME, bytes([10]))).updated
assert session.snapshot.generation == 6
assert (session.snapshot.txdelay, session.snapshot.persist, session.snapshot.slottime) == (30, 0, 10)

obs = queue.observe_rssi(now=0.00, raw_magnitude=106)
assert obs.request_state is KISSDataRequestState.ACCESS
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.RECENT_RX
assert obs.access.csma.state is CSMAState.WAIT_CLEAR

obs = queue.observe_rssi(now=0.26, raw_magnitude=106)
assert obs.access is not None
assert obs.access.detector.state is ChannelBusyState.CLEAR
assert obs.access.csma.state is CSMAState.WAIT_SLOT
# Captured SLOTTIME=20 means the due time is 0.46, not the live value's 0.36.
assert abs(obs.access.csma.next_slot_at - 0.46) < 1e-9

not_due_rng = Bytes([100])
obs = queue.observe_rssi(now=0.37, raw_magnitude=106, random_byte_source=not_due_rng)
assert obs.request_state is KISSDataRequestState.ACCESS
assert obs.access is not None and obs.access.csma.state is CSMAState.WAIT_SLOT
assert not_due_rng.calls == 0
assert rec.calls == []

# Captured PERSIST=200 accepts byte 100.  The live post-admission PERSIST=0
# would not, so successful dispatch here proves per-request persistence capture.
rng = Bytes([100])
obs = queue.observe_rssi(now=0.47, raw_magnitude=106, random_byte_source=rng)
assert obs.request_state is KISSDataRequestState.DISPATCHED
assert obs.parameter_generation == 3
assert obs.access is not None and obs.access.csma.state is CSMAState.READY
assert rng.calls == 1
assert len(rec.calls) == 1
sent, sent_context, sent_timeout = rec.calls[0]
assert sent[:-2] == body
assert verify_fcs(sent)
assert sent_context.parameters.generation == 3
assert (sent_context.parameters.txdelay, sent_context.parameters.persist, sent_context.parameters.slottime) == (50, 200, 20)
assert sent_timeout == 1.5
assert queue.snapshot.queue_depth == 0
assert queue.snapshot.dispatched_requests == 1

# Later observations can never duplicate a consumed request.
queue.observe_rssi(now=0.60, raw_magnitude=48, random_byte_source=Bytes([0]))
assert len(rec.calls) == 1

# KISS ingress is frame-without-FCS.  Malformed AX.25 is rejected before queueing.
badq = KISSDataAdmissionQueue(Recorder())
try:
    badq.enqueue(b"not-an-ax25-frame", session.capture_tx_context(), now=1.0)
except KISSDataFrameRejected:
    pass
else:
    raise AssertionError("malformed KISS DATA entered P7 queue")
assert badq.snapshot.invalid_rejections == 1
assert badq.snapshot.queue_depth == 0

# Capacity is strict and includes the current head request.
small = KISSDataAdmissionQueue(Recorder(), queue_capacity=2)
ctx = session.capture_tx_context()
small.enqueue(kiss_body("Q1"), ctx, now=2.0)
small.enqueue(kiss_body("Q2"), ctx, now=2.0)
try:
    small.enqueue(kiss_body("Q3"), ctx, now=2.0)
except KISSDataQueueFull:
    pass
else:
    raise AssertionError("P7 queue accepted over capacity")
assert small.snapshot.queue_depth == 2
assert small.snapshot.queue_full_rejections == 1

# Downstream failure is terminal and cannot be retried by later RSSI samples.
fail_rec = Recorder(fail=True)
failq = KISSDataAdmissionQueue(fail_rec)
failq.enqueue(kiss_body("FAIL"), ctx, now=10.0)
failq.observe_rssi(now=10.00, raw_magnitude=106)
failq.observe_rssi(now=10.26, raw_magnitude=106)
obs = failq.observe_rssi(now=10.37, raw_magnitude=106, random_byte_source=Bytes([0]))
assert obs.request_state is KISSDataRequestState.DOWNSTREAM_FAILED
assert obs.downstream_called is True
assert len(fail_rec.calls) == 1
failq.observe_rssi(now=10.50, raw_magnitude=106, random_byte_source=Bytes([0]))
assert len(fail_rec.calls) == 1
assert failq.snapshot.downstream_failures == 1

print("P7_KISS_DATA_ADMISSION=PASS")
print("KISS_DATA_FCS_OWNER=TNC_APPEND_EXACTLY_ONCE")
print("P6_CONTEXT_CAPTURE=IMMUTABLE_PER_REQUEST")
print("CAPTURED_TXDELAY=PASS")
print("CAPTURED_PERSIST=PASS")
print("CAPTURED_SLOTTIME=PASS")
print("QUEUE_CAPACITY=BOUNDED")
print("READY_DISPATCH_EXACTLY_ONCE=PASS")
print("DOWNSTREAM_FAILURE_RETRY=NO")
print("MODEM_UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
