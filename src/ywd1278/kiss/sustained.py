"""Sustained KISS service adapters for YWD-1278 0C-P8.

P7 intentionally qualified a one-shot DATA admission path and therefore did
not need concurrent KISS producer threads racing a scheduler consumer.  P8
preserves the frozen P7 queue unchanged and adds one narrow lock-owning
composition wrapper around it.

This module also adds connection accounting to the existing threaded KISS
backend.  It has no modem, UART, serial, RF, GPIO, firmware, clock, RNG, or
transmit implementation of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
import threading
from typing import Callable

from .control import TNCSessionState
from .server import PacketEvent
from .tx_backend import TNCTransmitBackend
from .tx_path import (
    KISSDataAdmissionQueue,
    KISSDataQueueObservation,
    KISSDataQueueSnapshot,
    KISSDataRequestReceipt,
    ContextualFrameSubmitter,
    RandomByteSource,
)


@dataclass(frozen=True)
class KISSConnectionCounters:
    total_connections: int
    total_disconnects: int
    active_connections: int


class ThreadSafeKISSDataAdmissionQueue:
    """Serialize concurrent P8 producers/consumer around the frozen P7 queue.

    The lock is intentionally held through ``observe_rssi`` including a
    synchronous downstream dispatch.  That means a KISS client may briefly
    wait while one half-duplex TX cycle completes, but it also guarantees that
    no producer can mutate the deque while READY is being consumed.
    """

    def __init__(
        self,
        submitter: ContextualFrameSubmitter,
        *,
        queue_capacity: int = 4,
        request_timeout_seconds: float = 30.0,
        downstream_timeout_seconds: float = 1.5,
    ) -> None:
        self._queue = KISSDataAdmissionQueue(
            submitter,
            queue_capacity=queue_capacity,
            request_timeout_seconds=request_timeout_seconds,
            downstream_timeout_seconds=downstream_timeout_seconds,
        )
        self._lock = threading.RLock()

    @property
    def request_timeout_seconds(self) -> float:
        return self._queue.request_timeout_seconds

    @property
    def snapshot(self) -> KISSDataQueueSnapshot:
        with self._lock:
            return self._queue.snapshot

    def enqueue(self, frame_no_fcs: bytes, context, *, now: float) -> KISSDataRequestReceipt:  # type: ignore[no-untyped-def]
        with self._lock:
            return self._queue.enqueue(frame_no_fcs, context, now=now)

    def observe_rssi(
        self,
        *,
        now: float,
        raw_magnitude: int,
        random_byte_source: RandomByteSource | None = None,
    ) -> KISSDataQueueObservation:
        with self._lock:
            return self._queue.observe_rssi(
                now=now,
                raw_magnitude=raw_magnitude,
                random_byte_source=random_byte_source,
            )


class SustainedTNCBackend(TNCTransmitBackend):
    """P7 TX backend plus total TCP client connect/disconnect accounting."""

    def __init__(
        self,
        admission: ThreadSafeKISSDataAdmissionQueue,
        *,
        monotonic: Callable[[], float],
        events: tuple[PacketEvent, ...] | list[PacketEvent] = (),
        session: TNCSessionState | None = None,
        history_capacity: int = 256,
        subscriber_queue_capacity: int = 64,
    ) -> None:
        super().__init__(
            admission,  # type: ignore[arg-type]
            monotonic=monotonic,
            events=events,
            session=session,
            history_capacity=history_capacity,
            subscriber_queue_capacity=subscriber_queue_capacity,
        )
        self._connection_lock = threading.Lock()
        self._connection_queues: set[Queue[PacketEvent]] = set()
        self._total_connections = 0
        self._total_disconnects = 0

    @property
    def connection_counters(self) -> KISSConnectionCounters:
        with self._connection_lock:
            return KISSConnectionCounters(
                total_connections=self._total_connections,
                total_disconnects=self._total_disconnects,
                active_connections=len(self._connection_queues),
            )

    def open_stream(self) -> tuple[list[PacketEvent], Queue[PacketEvent]]:
        history, queue = super().open_stream()
        with self._connection_lock:
            self._connection_queues.add(queue)
            self._total_connections += 1
        return history, queue

    def close_stream(self, queue: Queue[PacketEvent]) -> None:
        counted = False
        with self._connection_lock:
            if queue in self._connection_queues:
                self._connection_queues.remove(queue)
                self._total_disconnects += 1
                counted = True
        # Always preserve the base subscriber cleanup even if a future caller
        # accidentally closes the same stream twice.
        super().close_stream(queue)
