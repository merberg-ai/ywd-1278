"""0F-P5c2 shared classic beacon commands and product console composition."""

from __future__ import annotations

import threading
import time
from typing import Callable

from ywd1278.ax25 import Address
from ywd1278.console.classic_tx import ClassicTXCommandShell
from ywd1278.console.local import MAX_COMMAND_CHARS, CommandResult
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.service.classic_beacon import (
    ProductBeaconCoordinator,
    ProductBeaconSnapshot,
)
from ywd1278.service.classic_tx_console import ProductClassicTXConsole


class ThreadSafeProductBeaconCoordinator(ProductBeaconCoordinator):
    """Serialize console mutations and scheduler ticks around frozen P5b."""

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._state_lock = threading.RLock()
        super().__init__(**kwargs)

    @property
    def snapshot(self) -> ProductBeaconSnapshot:
        with self._state_lock:
            return super().snapshot

    def set_text(self, text: str) -> ProductBeaconSnapshot:
        with self._state_lock:
            return super().set_text(text)

    def arm(
        self,
        *,
        destination: Address,
        path: tuple[Address, ...] = (),
        interval_seconds: int,
        now: float,
    ) -> ProductBeaconSnapshot:
        with self._state_lock:
            return super().arm(
                destination=destination,
                path=path,
                interval_seconds=interval_seconds,
                now=now,
            )

    def off(self) -> ProductBeaconSnapshot:
        with self._state_lock:
            return super().off()

    def tick(self, *, now: float):  # type: ignore[no-untyped-def]
        with self._state_lock:
            return super().tick(now=now)


class ProductBeaconCommandShell(ClassicTXCommandShell):
    """Per-session P4 state plus one shared product beacon coordinator."""

    def __init__(
        self,
        *,
        beacon: ThreadSafeProductBeaconCoordinator,
        clock: Callable[[], float] = time.monotonic,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not isinstance(beacon, ThreadSafeProductBeaconCoordinator):
            raise TypeError("beacon must be ThreadSafeProductBeaconCoordinator")
        if not callable(clock):
            raise TypeError("clock must be callable")
        super().__init__(**kwargs)
        self._beacon = beacon
        self._clock = clock

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
            lines = tuple(
                item for item in base.lines if "BEACON/BTEXT/ID remain deferred" not in item
            )
            return CommandResult(
                lines
                + (
                    "BTEXT [text]              query/set shared beacon text",
                    "BEACON EVERY <seconds>    arm shared product schedule",
                    "BEACON OFF                cancel shared product schedule",
                    "BEACON                    show shared product schedule",
                    "ID                        non-transmitting; owned by 0F-P5e",
                )
            )
        if command == "BTEXT":
            return self._btext(argument)
        if command == "BEACON":
            return self._beacon_command(argument)
        if command == "ID":
            if argument:
                return CommandResult(("ERROR ID takes no arguments",))
            return CommandResult(("ID TX DEFERRED; OWNER=0F-P5e",))
        return super().execute(line)

    def _btext(self, argument: str) -> CommandResult:
        if not argument:
            text = self._beacon.snapshot.text
            return CommandResult(("BTEXT UNSET" if text is None else f"BTEXT {text}",))
        try:
            snapshot = self._beacon.set_text(argument)
        except (TypeError, ValueError) as exc:
            return CommandResult((f"ERROR BTEXT {exc}",))
        assert snapshot.text is not None
        return CommandResult((f"BTEXT SET BYTES={len(snapshot.text.encode('ascii'))}",))

    def _beacon_command(self, argument: str) -> CommandResult:
        if not argument:
            snapshot = self._beacon.snapshot
            schedule = snapshot.schedule
            if not schedule.enabled:
                return CommandResult(("BEACON OFF",))
            destination = snapshot.destination or "UNSET"
            via = "DIRECT" if not snapshot.path else ",".join(snapshot.path)
            return CommandResult(
                (
                    f"BEACON EVERY {schedule.interval_seconds} DEST={destination} "
                    f"VIA={via} NEXT={schedule.next_due_at:.6f}",
                )
            )
        parts = argument.split()
        if len(parts) == 1 and parts[0].upper() == "OFF":
            self._beacon.off()
            return CommandResult(("BEACON OFF",))
        if len(parts) != 2 or parts[0].upper() != "EVERY":
            return CommandResult(("ERROR BEACON expects EVERY <seconds> or OFF",))
        session = self.tx_snapshot
        if session.destination is None:
            return CommandResult(("ERROR BEACON requires UNPROTO destination",))
        try:
            interval = int(parts[1], 10)
            snapshot = self._beacon.arm(
                destination=Address.parse(session.destination),
                path=tuple(Address.parse(item) for item in session.path),
                interval_seconds=interval,
                now=self._clock(),
            )
        except (TypeError, ValueError) as exc:
            return CommandResult((f"ERROR BEACON {exc}",))
        policy = "TX-ELIGIBLE" if snapshot.tx_enabled else "TX-BLOCKED"
        return CommandResult(
            (
                f"BEACON EVERY {snapshot.schedule.interval_seconds} "
                f"NEXT={snapshot.schedule.next_due_at:.6f} {policy}",
            )
        )


class ProductClassicBeaconConsole(ProductClassicTXConsole):
    """P4 product console with one coordinator shared by every session."""

    def __init__(
        self,
        *args,  # type: ignore[no-untyped-def]
        beacon: ThreadSafeProductBeaconCoordinator,
        clock: Callable[[], float] = time.monotonic,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not isinstance(beacon, ThreadSafeProductBeaconCoordinator):
            raise TypeError("beacon must be ThreadSafeProductBeaconCoordinator")
        if not callable(clock):
            raise TypeError("clock must be callable")
        super().__init__(*args, **kwargs)
        self.beacon = beacon
        self._beacon_clock = clock

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        source = self.tx_config.source
        if source is None:
            return super()._shell_factory()
        return ProductBeaconCommandShell(
            source=source,
            paclen=self.tx_config.paclen,
            tx_enabled=self.tx_enabled,
            tx_submitter=self.tx_submitter,
            beacon=self.beacon,
            clock=self._beacon_clock,
            diagnostics=self._diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=self._mheard_db,
        )


__all__ = [
    "ProductBeaconCommandShell",
    "ProductClassicBeaconConsole",
    "ThreadSafeProductBeaconCoordinator",
]
