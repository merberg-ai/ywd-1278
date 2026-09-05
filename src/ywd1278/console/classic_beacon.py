"""Host-only 0F-P5a classic BTEXT/beacon state machine.

This layer extends the frozen P1/P2 shell without owning a clock thread, TX
callback, queue, modem, UART, or RF path.  Callers explicitly poll
``take_due_beacon``.  A due result is only an immutable AX.25 UI frame body;
P5a never admits it for transmission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import time

from ywd1278.ax25 import Address, build_ui_frame
from ywd1278.console.classic_tx import ClassicTXCommandShell
from ywd1278.console.local import MAX_COMMAND_CHARS, CommandResult


MIN_BEACON_INTERVAL_SECONDS = 10
MAX_BEACON_INTERVAL_SECONDS = 86_400


@dataclass(frozen=True)
class BeaconScheduleSnapshot:
    enabled: bool
    interval_seconds: int | None
    next_due_at: float | None
    generation: int
    emitted_events: int


@dataclass(frozen=True)
class BeaconDueEvent:
    generation: int
    due_at: float
    observed_at: float
    frame_no_fcs: bytes


class DeterministicBeaconSchedule:
    """Explicitly-polled schedule with no catch-up and no side effects."""

    def __init__(self) -> None:
        self._enabled = False
        self._interval_seconds: int | None = None
        self._next_due_at: float | None = None
        self._generation = 0
        self._emitted_events = 0

    @property
    def snapshot(self) -> BeaconScheduleSnapshot:
        return BeaconScheduleSnapshot(
            enabled=self._enabled,
            interval_seconds=self._interval_seconds,
            next_due_at=self._next_due_at,
            generation=self._generation,
            emitted_events=self._emitted_events,
        )

    def every(self, interval_seconds: int, *, now: float) -> BeaconScheduleSnapshot:
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
            raise TypeError("beacon interval must be an integer")
        if not MIN_BEACON_INTERVAL_SECONDS <= interval_seconds <= MAX_BEACON_INTERVAL_SECONDS:
            raise ValueError(
                f"beacon interval must be {MIN_BEACON_INTERVAL_SECONDS}.."
                f"{MAX_BEACON_INTERVAL_SECONDS} seconds"
            )
        self._generation += 1
        self._enabled = True
        self._interval_seconds = interval_seconds
        self._next_due_at = float(now) + interval_seconds
        return self.snapshot

    def off(self) -> BeaconScheduleSnapshot:
        self._generation += 1
        self._enabled = False
        self._interval_seconds = None
        self._next_due_at = None
        return self.snapshot

    def take_due(self, *, now: float) -> tuple[int, float] | None:
        if not self._enabled or self._next_due_at is None or self._interval_seconds is None:
            return None
        observed = float(now)
        if observed < self._next_due_at:
            return None
        due_at = self._next_due_at
        # Schedule from observation time.  Missed periods are discarded rather
        # than replayed as a catch-up burst.
        self._next_due_at = observed + self._interval_seconds
        self._emitted_events += 1
        return self._generation, due_at


class ClassicBeaconCommandShell(ClassicTXCommandShell):
    """P1/P2 shell plus inert, deterministic P5a beacon configuration."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not callable(clock):
            raise TypeError("clock must be callable")
        super().__init__(**kwargs)
        self._clock = clock
        self._btext: bytes | None = None
        self._beacon_schedule = DeterministicBeaconSchedule()

    @property
    def beacon_snapshot(self) -> BeaconScheduleSnapshot:
        return self._beacon_schedule.snapshot

    @property
    def btext(self) -> str | None:
        return None if self._btext is None else self._btext.decode("ascii")

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        if "\x00" in line or self.tx_snapshot.converse_mode:
            return super().execute(line)

        normalized = line.strip(" \t\r\n")
        if len(normalized) > MAX_COMMAND_CHARS or not normalized:
            return super().execute(line)
        command, _, argument = normalized.partition(" ")
        command = command.upper()
        argument = argument.strip()

        if command in ("HELP", "?") and not argument:
            base = super().execute("HELP")
            filtered = tuple(
                item for item in base.lines if "BEACON/BTEXT/ID remain deferred" not in item
            )
            return CommandResult(
                filtered
                + (
                    "BTEXT [text]              query/set bounded beacon text",
                    "BEACON EVERY <seconds>    arm host schedule state",
                    "BEACON OFF                cancel host schedule state",
                    "BEACON                    show host schedule state",
                    "ID                        non-transmitting in P5a; RF semantics deferred",
                    "NOTE                      P5a has no timer thread or TX admission",
                )
            )
        if command == "BTEXT":
            return self._execute_btext(argument)
        if command == "BEACON":
            return self._execute_beacon(argument)
        if command == "ID":
            if argument:
                return CommandResult(("ERROR ID takes no arguments",))
            return CommandResult(("ID TX DEFERRED; OWNER=0F-P5e",))
        return super().execute(line)

    def _execute_btext(self, argument: str) -> CommandResult:
        if not argument:
            if self._btext is None:
                return CommandResult(("BTEXT UNSET",))
            return CommandResult((f"BTEXT {self.btext}",))
        try:
            encoded = argument.encode("ascii")
        except UnicodeEncodeError:
            return CommandResult(("ERROR BTEXT must be ASCII",))
        if any(value < 32 or value > 126 for value in encoded):
            return CommandResult(("ERROR BTEXT must contain printable ASCII only",))
        if len(encoded) > self.tx_snapshot.paclen:
            return CommandResult((f"ERROR BTEXT exceeds PACLEN {self.tx_snapshot.paclen}",))
        self._btext = encoded
        return CommandResult((f"BTEXT SET BYTES={len(encoded)}",))

    def _execute_beacon(self, argument: str) -> CommandResult:
        if not argument:
            state = self.beacon_snapshot
            if not state.enabled:
                return CommandResult(("BEACON OFF",))
            return CommandResult(
                (f"BEACON EVERY {state.interval_seconds} NEXT={state.next_due_at:.6f}",)
            )
        parts = argument.split()
        if len(parts) == 1 and parts[0].upper() == "OFF":
            self._beacon_schedule.off()
            return CommandResult(("BEACON OFF",))
        if len(parts) != 2 or parts[0].upper() != "EVERY":
            return CommandResult(("ERROR BEACON expects EVERY <seconds> or OFF",))
        if self._btext is None:
            return CommandResult(("ERROR BEACON requires BTEXT",))
        if self.tx_snapshot.destination is None:
            return CommandResult(("ERROR BEACON requires UNPROTO destination",))
        try:
            interval = int(parts[1], 10)
            state = self._beacon_schedule.every(interval, now=self._clock())
        except (TypeError, ValueError) as exc:
            return CommandResult((f"ERROR BEACON {exc}",))
        policy = "TX-ELIGIBLE" if self.tx_snapshot.tx_enabled else "TX-BLOCKED"
        return CommandResult(
            (f"BEACON EVERY {state.interval_seconds} NEXT={state.next_due_at:.6f} {policy}",)
        )

    def take_due_beacon(self, *, now: float | None = None) -> BeaconDueEvent | None:
        """Return at most one inert frame body; never call a TX submitter."""

        if not self.tx_snapshot.tx_enabled or self._btext is None:
            return None
        destination_text = self.tx_snapshot.destination
        if destination_text is None:
            return None
        observed = self._clock() if now is None else float(now)
        due = self._beacon_schedule.take_due(now=observed)
        if due is None:
            return None
        generation, due_at = due
        frame = build_ui_frame(
            source=Address.parse(self.tx_snapshot.source),
            destination=Address.parse(destination_text),
            path=tuple(Address.parse(item) for item in self.tx_snapshot.path),
            info=self._btext,
            include_fcs=False,
        )
        return BeaconDueEvent(generation, due_at, observed, frame)


__all__ = [
    "BeaconDueEvent",
    "BeaconScheduleSnapshot",
    "ClassicBeaconCommandShell",
    "DeterministicBeaconSchedule",
    "MAX_BEACON_INTERVAL_SECONDS",
    "MIN_BEACON_INTERVAL_SECONDS",
]
