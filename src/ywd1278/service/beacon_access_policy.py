"""0F-P6 bounded beacon jitter above the frozen P5 coordinator."""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Callable

from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.service.product_beacon_console import ThreadSafeProductBeaconCoordinator


MAX_JITTER_SECONDS = 60.0
JITTER_FRACTION = 0.10


def secure_random_byte() -> int:
    return secrets.randbelow(256)


@dataclass(frozen=True)
class BeaconJitterSnapshot:
    generation: int | None
    base_due_at: float | None
    jitter_seconds: float | None
    eligible_at: float | None
    selections: int


class JitteredThreadSafeProductBeaconCoordinator(ThreadSafeProductBeaconCoordinator):
    """Delay each P5 due event by one bounded, non-negative random offset.

    Once eligible, ``super().tick`` still performs exactly one admission into
    the existing product DATA queue. That frozen queue remains the sole owner
    of channel-clear, p-persistence, half-duplex, and modem dispatch policy.
    """

    def __init__(
        self,
        *,
        jitter_byte_source: Callable[[], int] = secure_random_byte,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not callable(jitter_byte_source):
            raise TypeError("jitter_byte_source must be callable")
        self._jitter_byte_source = jitter_byte_source
        self._jitter_generation: int | None = None
        self._jitter_base_due_at: float | None = None
        self._jitter_seconds: float | None = None
        self._jitter_eligible_at: float | None = None
        self._jitter_selections = 0
        super().__init__(**kwargs)

    @property
    def jitter_snapshot(self) -> BeaconJitterSnapshot:
        with self._state_lock:
            return BeaconJitterSnapshot(
                generation=self._jitter_generation,
                base_due_at=self._jitter_base_due_at,
                jitter_seconds=self._jitter_seconds,
                eligible_at=self._jitter_eligible_at,
                selections=self._jitter_selections,
            )

    def arm(self, **kwargs):  # type: ignore[no-untyped-def]
        with self._state_lock:
            snapshot = super().arm(**kwargs)
            try:
                self._select_for(snapshot.schedule)
            except Exception:
                super().off()
                self._clear_jitter()
                raise
            return snapshot

    def off(self):  # type: ignore[no-untyped-def]
        with self._state_lock:
            snapshot = super().off()
            self._clear_jitter()
            return snapshot

    def tick(self, *, now: float) -> ClassicTXSubmitResult | None:
        with self._state_lock:
            schedule = self.snapshot.schedule
            if not schedule.enabled or schedule.next_due_at is None:
                self._clear_jitter()
                return None
            if (
                self._jitter_generation != schedule.generation
                or self._jitter_base_due_at != schedule.next_due_at
            ):
                self._select_for(schedule)
            assert self._jitter_eligible_at is not None
            if float(now) < self._jitter_eligible_at:
                return None
            result = super().tick(now=now)
            updated = self.snapshot.schedule
            if updated.enabled and updated.next_due_at is not None:
                self._select_for(updated)
            else:
                self._clear_jitter()
            return result

    def _select_for(self, schedule) -> None:  # type: ignore[no-untyped-def]
        if schedule.next_due_at is None or schedule.interval_seconds is None:
            self._clear_jitter()
            return
        value = self._jitter_byte_source()
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError("jitter byte source must return an integer 0..255")
        maximum = min(MAX_JITTER_SECONDS, schedule.interval_seconds * JITTER_FRACTION)
        offset = maximum * value / 255.0
        self._jitter_generation = schedule.generation
        self._jitter_base_due_at = schedule.next_due_at
        self._jitter_seconds = offset
        self._jitter_eligible_at = schedule.next_due_at + offset
        self._jitter_selections += 1

    def _clear_jitter(self) -> None:
        self._jitter_generation = None
        self._jitter_base_due_at = None
        self._jitter_seconds = None
        self._jitter_eligible_at = None


__all__ = [
    "BeaconJitterSnapshot",
    "JITTER_FRACTION",
    "JitteredThreadSafeProductBeaconCoordinator",
    "MAX_JITTER_SECONDS",
]
