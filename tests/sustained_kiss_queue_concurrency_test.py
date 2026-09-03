#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.kiss.control import TNCSessionState  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSMessage  # noqa: E402
from ywd1278.kiss.sustained import SustainedTNCBackend, ThreadSafeKISSDataAdmissionQueue  # noqa: E402


class NeverSubmit:
    def submit_frame(self, frame_with_fcs: bytes, context, *, timeout=None):  # type: ignore[no-untyped-def]
        raise AssertionError("concurrency admission test must not dispatch")


def body(index: int) -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD8"),
        path=[Address.parse("YWDNOD")],
        info=f"P8 CONCURRENCY {index}".encode("ascii"),
        include_fcs=False,
    )


# First lock the race that motivated P8's serialized clock sampling.  The
# historical P7 call shape can hand the wrapper stale pre-lock ``now`` values,
# but the explicitly injected clock is sampled only after queue serialization.
class OrderedClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            self.value += 1.0
            return self.value


ordered_clock = OrderedClock()
race_queue = ThreadSafeKISSDataAdmissionQueue(
    NeverSubmit(),
    monotonic=ordered_clock,
    queue_capacity=1,
    request_timeout_seconds=30.0,
)
race_session = TNCSessionState()
race_context = race_session.capture_tx_context(max_wait_seconds=30.0)
race_receipt = race_queue.enqueue(body(99), race_context, now=1000.0)
assert race_receipt.enqueued_at == 1.0
race_observation = race_queue.observe_rssi(
    now=0.0,  # intentionally older external sample; must not reach frozen P7
    raw_magnitude=106,
)
assert race_observation.now == 2.0
assert race_queue.snapshot.queue_depth == 1


# Then prove actual simultaneous producer pressure remains bounded/correct.
static_clock = lambda: 1.0
admission = ThreadSafeKISSDataAdmissionQueue(
    NeverSubmit(),
    monotonic=static_clock,
    queue_capacity=4,
    request_timeout_seconds=30.0,
)
backend = SustainedTNCBackend(
    admission,
    monotonic=static_clock,
    session=TNCSessionState(),
    history_capacity=0,
)
barrier = threading.Barrier(9)
results = []
errors = []
lock = threading.Lock()


def producer(index: int) -> None:
    try:
        barrier.wait(timeout=2.0)
        result = backend.reject_client_message(KISSMessage(0, DATA, body(index)))
        with lock:
            results.append(result)
    except BaseException as exc:
        with lock:
            errors.append(exc)


threads = [threading.Thread(target=producer, args=(i,), daemon=True) for i in range(8)]
for thread in threads:
    thread.start()
barrier.wait(timeout=2.0)
for thread in threads:
    thread.join(timeout=2.0)
    assert not thread.is_alive()

assert not errors, errors
assert len(results) == 8
assert sum(1 for result in results if result.admitted) == 4
assert sum(1 for result in results if not result.admitted) == 4
assert admission.snapshot.queue_depth == 4
assert admission.snapshot.accepted_requests == 4
assert admission.snapshot.queue_full_rejections == 4
assert backend.ingress_counters.data_messages_received == 8
assert backend.ingress_counters.data_admitted == 4
assert backend.ingress_counters.data_queue_full_drops == 4
assert backend.ingress_counters.data_invalid_rejections == 0
assert backend.ingress_counters.data_other_rejections == 0
assert backend.control_snapshot.generation == 0

print("P8_THREAD_SAFE_KISS_ADMISSION_CONCURRENCY=PASS")
print("SERIALIZED_QUEUE_CLOCK_SAMPLING=PASS")
print("STALE_PRELOCK_TIMESTAMP_REJECTED_FROM_P7=PASS")
print("CONCURRENT_PRODUCERS=8")
print("QUEUE_CAPACITY=4")
print("DATA_ADMITTED=4")
print("QUEUE_FULL_DROPS=4")
print("QUEUE_CORRUPTION=NO")
print("DOWNSTREAM_CALLED=NO")
print("HARDWARE_DEPENDENCY=NO")
print("RF_TRANSMITTED=NO")
