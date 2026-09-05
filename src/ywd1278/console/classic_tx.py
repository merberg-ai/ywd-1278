"""0F classic UNPROTO/converse transmit personality.

This layer deliberately subclasses the frozen 0E-P5 ``ClassicTNCCommandShell``
instead of editing it.  It owns only per-session UI-frame state and converts
one bounded converse line into one AX.25 UI frame body.  Actual admission,
CSMA, modem ownership, half-duplex switching, and RF remain owned by the
already-qualified product TX graph.

Safety properties:

* no transport, UART, modem, GPIO, firmware, timer, or RF ownership;
* no automatic retry and no background transmitter;
* ``radio.tx_enabled=false`` fails closed before invoking the submit callback;
* one converse input line can invoke the submit callback at most once;
* AX.25 FCS is deliberately omitted here because the frozen KISS DATA
  admission boundary appends it exactly once;
* BEACON/BTEXT/ID remain deferred to a later 0F slice;
* connected mode remains owned by 0G.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ywd1278 import __version__
from ywd1278.ax25 import Address, build_ui_frame
from ywd1278.console.classic import ClassicTNCCommandShell
from ywd1278.console.local import MAX_COMMAND_CHARS, CommandResult
from ywd1278.monitor.policy import MonitorPolicyState


MAX_UNPROTO_DIGIPEATERS = 8
DEFAULT_PACLEN = 128
MAX_PACLEN = 256
COMMAND_MODE_ESCAPE = "COMMAND"


@dataclass(frozen=True)
class ClassicTXSubmitResult:
    admitted: bool
    request_id: int | None
    reason: str


ClassicTXSubmitter = Callable[[bytes], ClassicTXSubmitResult]


@dataclass(frozen=True)
class ClassicTXSessionSnapshot:
    source: str
    destination: str | None
    path: tuple[str, ...]
    converse_mode: bool
    tx_enabled: bool
    paclen: int
    admitted_lines: int


def _ascii_info(line: str, *, paclen: int) -> bytes:
    try:
        encoded = line.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("converse text must be ASCII") from exc
    if any(value < 32 or value > 126 for value in encoded):
        raise ValueError("converse text must contain printable ASCII only")
    if len(encoded) > paclen:
        raise ValueError(f"converse text exceeds PACLEN {paclen}")
    return encoded


def _parse_unproto(args: list[str]) -> tuple[Address, tuple[Address, ...]]:
    if not args:
        raise ValueError("UNPROTO destination is required")
    try:
        destination = Address.parse(args[0])
    except ValueError as exc:
        raise ValueError(f"invalid UNPROTO destination: {exc}") from exc

    if len(args) == 1:
        return destination, ()
    if args[1].upper() != "VIA":
        raise ValueError("UNPROTO syntax is DEST [VIA DIGI[,DIGI...]]")
    if len(args) == 2:
        raise ValueError("UNPROTO VIA requires at least one digipeater")

    tokens: list[str] = []
    for item in args[2:]:
        tokens.extend(token for token in item.split(",") if token)
    if not tokens:
        raise ValueError("UNPROTO VIA requires at least one digipeater")
    if len(tokens) > MAX_UNPROTO_DIGIPEATERS:
        raise ValueError(
            f"UNPROTO path exceeds {MAX_UNPROTO_DIGIPEATERS} digipeaters"
        )

    path: list[Address] = []
    for token in tokens:
        try:
            path.append(Address.parse(token))
        except ValueError as exc:
            raise ValueError(f"invalid UNPROTO digipeater {token!r}: {exc}") from exc
    return destination, tuple(path)


class ClassicTXCommandShell(ClassicTNCCommandShell):
    """Frozen P5 personality plus bounded per-session 0F UI transmit state."""

    def __init__(
        self,
        *,
        source: Address,
        paclen: int = DEFAULT_PACLEN,
        tx_enabled: bool = False,
        tx_submitter: ClassicTXSubmitter | None = None,
        diagnostics: Any = None,
        monitor_policy: MonitorPolicyState | None = None,
        mheard_db: Any = None,
        version: str = __version__,
    ) -> None:
        if not isinstance(source, Address):
            raise TypeError("source must be an AX.25 Address")
        if isinstance(paclen, bool) or not isinstance(paclen, int):
            raise TypeError("paclen must be an integer")
        if not 1 <= paclen <= MAX_PACLEN:
            raise ValueError(f"paclen must be 1..{MAX_PACLEN}")
        if tx_submitter is not None and not callable(tx_submitter):
            raise TypeError("tx_submitter must be callable or None")
        super().__init__(
            diagnostics=diagnostics,
            monitor_policy=monitor_policy,
            mheard_db=mheard_db,
            version=version,
        )
        self._source = source
        self._paclen = int(paclen)
        self._tx_enabled = bool(tx_enabled)
        self._tx_submitter = tx_submitter
        self._destination: Address | None = None
        self._path: tuple[Address, ...] = ()
        self._converse_mode = False
        self._admitted_lines = 0

    @property
    def tx_snapshot(self) -> ClassicTXSessionSnapshot:
        return ClassicTXSessionSnapshot(
            source=str(self._source),
            destination=None if self._destination is None else str(self._destination),
            path=tuple(str(item) for item in self._path),
            converse_mode=self._converse_mode,
            tx_enabled=self._tx_enabled,
            paclen=self._paclen,
            admitted_lines=self._admitted_lines,
        )

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        if "\x00" in line:
            return super().execute(line)

        if self._converse_mode:
            return self._execute_converse(line)

        normalized = line.strip(" \t\r\n")
        if len(normalized) > MAX_COMMAND_CHARS or not normalized:
            return super().execute(line)
        parts = normalized.split()
        command = parts[0].upper()
        args = parts[1:]

        if command in ("HELP", "?") and not args:
            base = super().execute("HELP")
            return CommandResult(
                base.lines
                + (
                    "UNPROTO [DEST [VIA PATH]]  query/set UI destination/path",
                    "CONVERSE                  enter line-oriented UI text mode",
                    "COMMAND                   return/stay in command mode",
                    f"NOTE                     converse escape is exact word {COMMAND_MODE_ESCAPE}",
                    "NOTE                     BEACON/BTEXT/ID remain deferred in this 0F slice",
                )
            )

        if command == "UNPROTO":
            return self._unproto(args)
        if command == "CONVERSE":
            return self._enter_converse(args)
        if command == COMMAND_MODE_ESCAPE:
            if args:
                return CommandResult(("ERROR COMMAND takes no arguments",))
            return CommandResult(("COMMAND MODE",))
        if command in ("BEACON", "BTEXT", "ID"):
            return CommandResult(
                (f"ERROR {command} NOT AVAILABLE IN 0F-P1/P2; OWNER=0F-P5",)
            )

        return super().execute(line)

    def _unproto(self, args: list[str]) -> CommandResult:
        if not args:
            if self._destination is None:
                return CommandResult(("UNPROTO UNSET",))
            via = "DIRECT" if not self._path else ",".join(str(item) for item in self._path)
            return CommandResult((f"UNPROTO DEST={self._destination} VIA={via}",))
        try:
            destination, path = _parse_unproto(args)
        except ValueError as exc:
            return CommandResult((f"ERROR UNPROTO {exc}",))
        self._destination = destination
        self._path = path
        via = "DIRECT" if not path else ",".join(str(item) for item in path)
        return CommandResult((f"UNPROTO DEST={destination} VIA={via}",))

    def _enter_converse(self, args: list[str]) -> CommandResult:
        if args:
            return CommandResult(("ERROR CONVERSE takes no arguments",))
        if self._destination is None:
            return CommandResult(("ERROR CONVERSE requires UNPROTO destination",))
        if not self._tx_enabled:
            return CommandResult(("ERROR CONVERSE TX DISABLED; radio.tx_enabled=false",))
        if self._tx_submitter is None:
            return CommandResult(("ERROR CONVERSE TX UNAVAILABLE",))
        self._converse_mode = True
        via = "DIRECT" if not self._path else ",".join(str(item) for item in self._path)
        return CommandResult(
            (
                f"CONVERSE MODE DEST={self._destination} VIA={via}",
                f"TYPE {COMMAND_MODE_ESCAPE} ON A LINE BY ITSELF TO RETURN TO COMMAND MODE",
            )
        )

    def _execute_converse(self, line: str) -> CommandResult:
        stripped = line.rstrip("\r\n")
        if stripped.strip().upper() == COMMAND_MODE_ESCAPE:
            self._converse_mode = False
            return CommandResult(("COMMAND MODE",))
        if stripped == "":
            return CommandResult(("CONVERSE EMPTY LINE NOT SENT",))
        if self._destination is None:
            # This should be unreachable because UNPROTO is required to enter,
            # but fail closed if future code mutates session state incorrectly.
            self._converse_mode = False
            return CommandResult(("ERROR CONVERSE LOST UNPROTO STATE; COMMAND MODE",))
        if not self._tx_enabled:
            self._converse_mode = False
            return CommandResult(("ERROR TX DISABLED; COMMAND MODE",))
        submitter = self._tx_submitter
        if submitter is None:
            self._converse_mode = False
            return CommandResult(("ERROR TX UNAVAILABLE; COMMAND MODE",))

        try:
            info = _ascii_info(stripped, paclen=self._paclen)
            frame_no_fcs = build_ui_frame(
                source=self._source,
                destination=self._destination,
                path=self._path,
                info=info,
                include_fcs=False,
            )
            result = submitter(frame_no_fcs)
        except Exception as exc:
            return CommandResult(
                (f"ERROR TX SUBMIT {type(exc).__name__}: {str(exc)[:120]}",)
            )
        if not isinstance(result, ClassicTXSubmitResult):
            return CommandResult(("ERROR TX SUBMIT invalid submitter result",))
        if not result.admitted:
            reason = result.reason.replace("\r", "\\r").replace("\n", "\\n")[:160]
            return CommandResult((f"ERROR TX REJECTED {reason}",))

        self._admitted_lines += 1
        request = "-" if result.request_id is None else str(result.request_id)
        via = "DIRECT" if not self._path else ",".join(str(item) for item in self._path)
        return CommandResult(
            (
                f"TX QUEUED REQUEST={request} DEST={self._destination} VIA={via} INFO_BYTES={len(info)}",
            )
        )


def make_classic_tx_shell(
    *,
    source: Address,
    paclen: int = DEFAULT_PACLEN,
    tx_enabled: bool = False,
    tx_submitter: ClassicTXSubmitter | None = None,
    diagnostics: Any = None,
    monitor_policy: MonitorPolicyState | None = None,
    mheard_db: Any = None,
    version: str = __version__,
) -> ClassicTXCommandShell:
    return ClassicTXCommandShell(
        source=source,
        paclen=paclen,
        tx_enabled=tx_enabled,
        tx_submitter=tx_submitter,
        diagnostics=diagnostics,
        monitor_policy=monitor_policy or MonitorPolicyState(),
        mheard_db=mheard_db,
        version=version,
    )


__all__ = [
    "COMMAND_MODE_ESCAPE",
    "ClassicTXCommandShell",
    "ClassicTXSessionSnapshot",
    "ClassicTXSubmitResult",
    "ClassicTXSubmitter",
    "DEFAULT_PACLEN",
    "MAX_PACLEN",
    "MAX_UNPROTO_DIGIPEATERS",
    "make_classic_tx_shell",
]
