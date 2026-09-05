"""0F-P5e manual one-shot classic ID command composition."""

from __future__ import annotations

from dataclasses import dataclass

from ywd1278.ax25 import Address, build_ui_frame
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.console.local import MAX_COMMAND_CHARS, CommandResult
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.service.product_beacon_console import (
    ProductBeaconCommandShell,
    ProductClassicBeaconConsole,
)


ID_DESTINATION = Address.parse("ID")
ID_TEXT_PREFIX = "YWD-1278 ID "


@dataclass(frozen=True)
class ProductIDSnapshot:
    attempts: int
    accepted: int
    last_result: ClassicTXSubmitResult | None


class ProductIDCommandShell(ProductBeaconCommandShell):
    """Shared-beacon shell plus a bounded manual identification command."""

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self._id_attempts = 0
        self._id_accepted = 0
        self._id_last_result: ClassicTXSubmitResult | None = None

    @property
    def id_snapshot(self) -> ProductIDSnapshot:
        return ProductIDSnapshot(
            attempts=self._id_attempts,
            accepted=self._id_accepted,
            last_result=self._id_last_result,
        )

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        if "\x00" in line or self.tx_snapshot.converse_mode:
            return super().execute(line)
        normalized = line.strip(" \t\r\n")
        if len(normalized) > MAX_COMMAND_CHARS or not normalized:
            return super().execute(line)
        parts = normalized.split()
        command = parts[0].upper()
        args = parts[1:]

        if command in ("HELP", "?") and not args:
            base = super().execute("HELP")
            lines = tuple(item for item in base.lines if not item.startswith("ID "))
            return CommandResult(
                lines
                + (
                    "ID                        send one direct manual station ID",
                    f"NOTE                      ID destination is {ID_DESTINATION}; no timer/retry",
                )
            )
        if command != "ID":
            return super().execute(line)
        if args:
            return CommandResult(("ERROR ID takes no arguments",))
        return self._send_id()

    def _send_id(self) -> CommandResult:
        session = self.tx_snapshot
        if not session.tx_enabled:
            return CommandResult(("ERROR ID TX DISABLED; radio.tx_enabled=false",))
        submitter = self._tx_submitter
        if submitter is None:
            return CommandResult(("ERROR ID TX UNAVAILABLE",))
        info = f"{ID_TEXT_PREFIX}{session.source}".encode("ascii")
        if len(info) > session.paclen:
            return CommandResult((f"ERROR ID text exceeds PACLEN {session.paclen}",))
        frame_no_fcs = build_ui_frame(
            source=Address.parse(session.source),
            destination=ID_DESTINATION,
            path=(),
            info=info,
            include_fcs=False,
        )
        self._id_attempts += 1
        try:
            result = submitter(frame_no_fcs)
        except Exception as exc:
            result = ClassicTXSubmitResult(
                False, None, f"{type(exc).__name__}: {str(exc)[:120]}"
            )
        if not isinstance(result, ClassicTXSubmitResult):
            result = ClassicTXSubmitResult(False, None, "invalid submitter result")
        self._id_last_result = result
        if not result.admitted:
            reason = result.reason.replace("\r", "\\r").replace("\n", "\\n")[:160]
            return CommandResult((f"ERROR ID REJECTED {reason}",))
        self._id_accepted += 1
        request = "-" if result.request_id is None else str(result.request_id)
        return CommandResult(
            (
                f"ID QUEUED REQUEST={request} DEST={ID_DESTINATION} VIA=DIRECT "
                f"INFO_BYTES={len(info)}",
            )
        )


class ProductClassicIDConsole(ProductClassicBeaconConsole):
    """P5c2 lifecycle selecting the P5e command shell per session."""

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        source = self.tx_config.source
        if source is None:
            return super()._shell_factory()
        return ProductIDCommandShell(
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
    "ID_DESTINATION",
    "ID_TEXT_PREFIX",
    "ProductClassicIDConsole",
    "ProductIDCommandShell",
    "ProductIDSnapshot",
]
