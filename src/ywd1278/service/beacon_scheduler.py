"""0F-P5c bounded lifecycle for the product beacon coordinator."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from ywd1278.service.classic_beacon import ProductBeaconCoordinator


@dataclass(frozen=True)
class BeaconSchedulerLifecycleSnapshot:
    running: bool
    starts: int
    stops: int
    ticks: int
    worker_failures: int


class ProductBeaconScheduler:
    """One cancellable polling worker; stopping always disarms beacon state."""

    def __init__(
        self,
        coordinator: ProductBeaconCoordinator,
        *,
        poll_interval_seconds: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(coordinator, ProductBeaconCoordinator):
            raise TypeError("coordinator must be ProductBeaconCoordinator")
        if isinstance(poll_interval_seconds, bool) or not isinstance(
            poll_interval_seconds, (int, float)
        ):
            raise TypeError("poll interval must be numeric")
        if not 0.01 <= float(poll_interval_seconds) <= 1.0:
            raise ValueError("poll interval must be 0.01..1.0 seconds")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._coordinator = coordinator
        self._poll_interval = float(poll_interval_seconds)
        self._clock = clock
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._starts = 0
        self._stops = 0
        self._ticks = 0
        self._worker_failures = 0

    @property
    def snapshot(self) -> BeaconSchedulerLifecycleSnapshot:
        with self._lock:
            thread = self._thread
            return BeaconSchedulerLifecycleSnapshot(
                running=thread is not None and thread.is_alive(),
                starts=self._starts,
                stops=self._stops,
                ticks=self._ticks,
                worker_failures=self._worker_failures,
            )

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("beacon scheduler already running")
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run,
                name="ywd1278-beacon-scheduler",
                daemon=False,
            )
            self._thread = thread
            self._starts += 1
            thread.start()

    def stop(self, *, join_timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(join_timeout_seconds)
            if thread.is_alive():
                raise RuntimeError("beacon scheduler did not stop")
        # Disarm only after the worker has joined, so stop cannot race an
        # in-flight coordinator tick while mutating schedule state.  Once stop
        # returns there is no worker and no inherited deadline.
        self._coordinator.off()
        with self._lock:
            if self._thread is not None:
                self._stops += 1
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                self._coordinator.tick(now=self._clock())
            except Exception:
                # A coordinator bug stops automatic operation instead of
                # spinning or retrying an uncertain admission.
                with self._lock:
                    self._worker_failures += 1
                self._stop_event.set()
                self._coordinator.off()
                return
            with self._lock:
                self._ticks += 1


__all__ = ["BeaconSchedulerLifecycleSnapshot", "ProductBeaconScheduler"]
