"""0F-P5b host composition for classic scheduled UI beacons.

The coordinator owns product-wide beacon state and converts one explicit due
tick into at most one call to the already-qualified classic TX submit adapter.
It owns no thread, clock, queue, CSMA implementation, modem, UART, or retry.
"""

from __future__ import annotations

from dataclasses import dataclass

from ywd1278.ax25 import Address, build_ui_frame
from ywd1278.console.classic_beacon import (
    BeaconScheduleSnapshot,
    DeterministicBeaconSchedule,
)
from ywd1278.console.classic_tx import ClassicTXSubmitResult, ClassicTXSubmitter


@dataclass(frozen=True)
class ProductBeaconSnapshot:
    source: str
    destination: str | None
    path: tuple[str, ...]
    text: str | None
    tx_enabled: bool
    schedule: BeaconScheduleSnapshot
    admission_attempts: int
    admissions_accepted: int
    last_result: ClassicTXSubmitResult | None


class ProductBeaconCoordinator:
    """Product-wide state with a caller-driven, single-attempt tick."""

    def __init__(
        self,
        *,
        source: Address,
        paclen: int,
        tx_enabled: bool,
        tx_submitter: ClassicTXSubmitter,
    ) -> None:
        if not isinstance(source, Address):
            raise TypeError("source must be an AX.25 Address")
        if isinstance(paclen, bool) or not isinstance(paclen, int) or not 1 <= paclen <= 256:
            raise ValueError("paclen must be an integer 1..256")
        if not callable(tx_submitter):
            raise TypeError("tx_submitter must be callable")
        self._source = source
        self._paclen = paclen
        self._tx_enabled = bool(tx_enabled)
        self._tx_submitter = tx_submitter
        self._destination: Address | None = None
        self._path: tuple[Address, ...] = ()
        self._text: bytes | None = None
        self._schedule = DeterministicBeaconSchedule()
        self._admission_attempts = 0
        self._admissions_accepted = 0
        self._last_result: ClassicTXSubmitResult | None = None

    @property
    def snapshot(self) -> ProductBeaconSnapshot:
        return ProductBeaconSnapshot(
            source=str(self._source),
            destination=None if self._destination is None else str(self._destination),
            path=tuple(str(item) for item in self._path),
            text=None if self._text is None else self._text.decode("ascii"),
            tx_enabled=self._tx_enabled,
            schedule=self._schedule.snapshot,
            admission_attempts=self._admission_attempts,
            admissions_accepted=self._admissions_accepted,
            last_result=self._last_result,
        )

    def set_text(self, text: str) -> ProductBeaconSnapshot:
        if not isinstance(text, str):
            raise TypeError("beacon text must be str")
        try:
            encoded = text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("beacon text must be ASCII") from exc
        if not encoded:
            raise ValueError("beacon text must not be empty")
        if any(value < 32 or value > 126 for value in encoded):
            raise ValueError("beacon text must contain printable ASCII only")
        if len(encoded) > self._paclen:
            raise ValueError(f"beacon text exceeds PACLEN {self._paclen}")
        self._text = encoded
        return self.snapshot

    def arm(
        self,
        *,
        destination: Address,
        path: tuple[Address, ...] = (),
        interval_seconds: int,
        now: float,
    ) -> ProductBeaconSnapshot:
        if not isinstance(destination, Address):
            raise TypeError("destination must be an AX.25 Address")
        if any(not isinstance(item, Address) for item in path):
            raise TypeError("path entries must be AX.25 Address values")
        if len(path) > 8:
            raise ValueError("beacon path exceeds 8 digipeaters")
        if self._text is None:
            raise ValueError("beacon text is unset")
        # Validate scheduling before replacing the last good destination/path.
        self._schedule.every(interval_seconds, now=now)
        self._destination = destination
        self._path = tuple(path)
        return self.snapshot

    def off(self) -> ProductBeaconSnapshot:
        self._schedule.off()
        return self.snapshot

    def tick(self, *, now: float) -> ClassicTXSubmitResult | None:
        """Attempt at most one existing-path admission for one due event."""

        if not self._tx_enabled:
            return None
        if self._destination is None or self._text is None:
            return None
        due = self._schedule.take_due(now=now)
        if due is None:
            return None
        frame_no_fcs = build_ui_frame(
            source=self._source,
            destination=self._destination,
            path=self._path,
            info=self._text,
            include_fcs=False,
        )
        self._admission_attempts += 1
        try:
            result = self._tx_submitter(frame_no_fcs)
        except Exception as exc:
            result = ClassicTXSubmitResult(
                False,
                None,
                f"{type(exc).__name__}: {str(exc)[:120]}",
            )
        if not isinstance(result, ClassicTXSubmitResult):
            result = ClassicTXSubmitResult(False, None, "invalid submitter result")
        self._last_result = result
        if result.admitted:
            self._admissions_accepted += 1
        return result


__all__ = ["ProductBeaconCoordinator", "ProductBeaconSnapshot"]
