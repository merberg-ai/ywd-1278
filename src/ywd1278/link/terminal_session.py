"""0G-P4 single connected-terminal policy above the frozen P3 link."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ywd1278.ax25 import Address
from ywd1278.link.modulo8 import LinkState
from ywd1278.link.timed_link import (
    LinkTimerConfig,
    TimedLinkResult,
    TimedModulo8DataLink,
)


MAX_TERMINAL_LINE_BYTES = 256


class TerminalMode(Enum):
    COMMAND = "COMMAND"
    CONNECTED = "CONNECTED"


@dataclass(frozen=True)
class ConnectedTerminalSnapshot:
    local: str
    remote: str | None
    mode: TerminalMode
    link_state: LinkState
    paclen: int
    maxframe: int
    submitted_lines: int
    delivered_lines: int
    rejected_lines: int


@dataclass(frozen=True)
class ConnectedTerminalResult:
    accepted: bool
    reason: str
    lines: tuple[str, ...] = ()
    link: TimedLinkResult | None = None


def _render_information(info: bytes) -> str:
    """Render received bytes without permitting terminal control injection."""

    return "".join(chr(value) if 32 <= value <= 126 else f"\\x{value:02x}" for value in info)


class ConnectedTerminalSession:
    """One deterministic command/data session; returned AX.25 actions are inert."""

    def __init__(
        self,
        *,
        local: Address,
        maxframe: int = 4,
        paclen: int = 128,
        timers: LinkTimerConfig = LinkTimerConfig(),
    ) -> None:
        if not isinstance(local, Address):
            raise TypeError("local must be an AX.25 Address")
        if isinstance(maxframe, bool) or not isinstance(maxframe, int) or not 1 <= maxframe <= 7:
            raise ValueError("maxframe must be an integer 1..7")
        if isinstance(paclen, bool) or not isinstance(paclen, int) or not 1 <= paclen <= 256:
            raise ValueError("paclen must be an integer 1..256")
        if not isinstance(timers, LinkTimerConfig):
            raise TypeError("timers must be LinkTimerConfig")
        self._local = Address(local.callsign, local.ssid)
        self._maxframe = maxframe
        self._paclen = paclen
        self._timers = timers
        self._remote: Address | None = None
        self._link: TimedModulo8DataLink | None = None
        self._mode = TerminalMode.COMMAND
        self._submitted_lines = 0
        self._delivered_lines = 0
        self._rejected_lines = 0
        self._failure_reported = False

    @property
    def snapshot(self) -> ConnectedTerminalSnapshot:
        state = LinkState.DISCONNECTED if self._link is None else self._link.snapshot.link.state
        return ConnectedTerminalSnapshot(
            local=str(self._local),
            remote=None if self._remote is None else str(self._remote),
            mode=self._mode,
            link_state=state,
            paclen=self._paclen,
            maxframe=self._maxframe,
            submitted_lines=self._submitted_lines,
            delivered_lines=self._delivered_lines,
            rejected_lines=self._rejected_lines,
        )

    def execute_line(self, line: str, *, now: float) -> ConnectedTerminalResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        normalized = line.rstrip("\r\n")
        if "\x00" in normalized or len(normalized.encode("utf-8")) > MAX_TERMINAL_LINE_BYTES:
            return self._reject("terminal line is invalid or exceeds 256 bytes")
        if self._mode is TerminalMode.CONNECTED:
            if normalized.strip().upper() == "COMMAND":
                self._mode = TerminalMode.COMMAND
                return ConnectedTerminalResult(True, "command mode", ("COMMAND MODE",))
            return self._send_text(normalized, now=now)

        stripped = normalized.strip(" \t")
        if not stripped:
            return self._reject("empty command")
        parts = stripped.split()
        command = parts[0].upper()
        args = parts[1:]
        if command in ("HELP", "?") and not args:
            return ConnectedTerminalResult(
                True,
                "help",
                (
                    "CONNECT DEST       begin one direct modulo-8 link",
                    "DISCONNECT         request orderly link release",
                    "CSTATUS            show this session's link status",
                    "CONVERSE           return to connected text mode",
                    "COMMAND            remain in command mode",
                ),
            )
        if command == "CONNECT":
            return self._connect(args, now=now)
        if command == "DISCONNECT":
            return self._disconnect(args, now=now)
        if command == "CSTATUS":
            if args:
                return self._reject("CSTATUS takes no arguments")
            return ConnectedTerminalResult(True, "status", (self._status_line(),))
        if command == "CONVERSE":
            if args:
                return self._reject("CONVERSE takes no arguments")
            if self.snapshot.link_state is not LinkState.CONNECTED:
                return self._reject("CONVERSE requires CONNECTED")
            self._mode = TerminalMode.CONNECTED
            return ConnectedTerminalResult(True, "connected text mode", ("CONNECTED MODE",))
        if command == "COMMAND" and not args:
            return ConnectedTerminalResult(True, "command mode", ("COMMAND MODE",))
        return self._reject(f"unknown connected-terminal command {command}")

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> ConnectedTerminalResult:
        if self._link is None:
            return self._reject("no link peer is selected")
        before = self._link.snapshot.link.state
        result = self._link.handle_frame(frame_no_fcs, now=now)
        lines: list[str] = []
        after = self._link.snapshot.link.state
        if result.accepted and before is not LinkState.CONNECTED and after is LinkState.CONNECTED:
            self._mode = TerminalMode.CONNECTED
            lines.append(f"CONNECTED TO {self._remote}")
        for info in result.delivered:
            self._delivered_lines += 1
            lines.append(_render_information(info))
        if after is LinkState.DISCONNECTED and before is not LinkState.DISCONNECTED:
            self._mode = TerminalMode.COMMAND
            lines.append(f"DISCONNECTED FROM {self._remote}")
        return ConnectedTerminalResult(result.accepted, result.reason, tuple(lines), result)

    def poll(self, *, now: float) -> ConnectedTerminalResult:
        if self._link is None:
            return ConnectedTerminalResult(True, "no link timer", (self._status_line(),))
        before = self._link.snapshot.link.state
        result = self._link.poll(now=now)
        after = self._link.snapshot.link.state
        lines: list[str] = []
        if self._link.snapshot.retry_exhausted and not self._failure_reported:
            self._mode = TerminalMode.COMMAND
            self._failure_reported = True
            lines.append(f"LINK FAILURE {self._remote}: {result.reason}")
        elif before is not LinkState.DISCONNECTED and after is LinkState.DISCONNECTED:
            self._mode = TerminalMode.COMMAND
            lines.append(f"DISCONNECTED FROM {self._remote}")
        return ConnectedTerminalResult(result.accepted, result.reason, tuple(lines), result)

    def _connect(self, args: list[str], *, now: float) -> ConnectedTerminalResult:
        if len(args) != 1:
            return self._reject("CONNECT syntax is CONNECT DEST")
        if self.snapshot.link_state is not LinkState.DISCONNECTED:
            return self._reject("CONNECT requires DISCONNECTED")
        try:
            remote = Address.parse(args[0])
        except ValueError as exc:
            return self._reject(f"invalid CONNECT destination: {exc}")
        if remote.callsign == self._local.callsign and remote.ssid == self._local.ssid:
            return self._reject("CONNECT destination must not be local station")
        self._remote = Address(remote.callsign, remote.ssid)
        self._failure_reported = False
        self._link = TimedModulo8DataLink(
            local=self._local,
            remote=self._remote,
            maxframe=self._maxframe,
            paclen=self._paclen,
            timers=self._timers,
        )
        result = self._link.connect(now=now)
        return ConnectedTerminalResult(
            result.accepted, result.reason, (f"CONNECTING TO {self._remote}",), result
        )

    def _disconnect(self, args: list[str], *, now: float) -> ConnectedTerminalResult:
        if args:
            return self._reject("DISCONNECT takes no arguments")
        if self._link is None or self.snapshot.link_state is LinkState.DISCONNECTED:
            return self._reject("DISCONNECT requires an active link")
        self._mode = TerminalMode.COMMAND
        result = self._link.disconnect(now=now)
        if self._link.snapshot.link.state is LinkState.DISCONNECTED:
            return ConnectedTerminalResult(
                result.accepted, result.reason, (f"DISCONNECTED FROM {self._remote}",), result
            )
        return ConnectedTerminalResult(
            result.accepted, result.reason, (f"DISCONNECTING FROM {self._remote}",), result
        )

    def _send_text(self, line: str, *, now: float) -> ConnectedTerminalResult:
        if not line:
            return self._reject("empty connected line not sent")
        try:
            info = line.encode("ascii")
        except UnicodeEncodeError:
            return self._reject("connected text must be ASCII")
        if any(value < 32 or value > 126 for value in info):
            return self._reject("connected text must contain printable ASCII only")
        if len(info) > self._paclen:
            return self._reject(f"connected text exceeds PACLEN {self._paclen}")
        assert self._link is not None
        result = self._link.send_information(info, now=now)
        if result.accepted:
            self._submitted_lines += 1
        else:
            self._rejected_lines += 1
        return ConnectedTerminalResult(result.accepted, result.reason, (), result)

    def _status_line(self) -> str:
        snap = self.snapshot
        remote = "NONE" if snap.remote is None else snap.remote
        return (
            f"CSTATUS STATE={snap.link_state.value} MODE={snap.mode.value} "
            f"REMOTE={remote} OUT={0 if self._link is None else self._link.snapshot.link.outstanding}"
        )

    def _reject(self, reason: str) -> ConnectedTerminalResult:
        self._rejected_lines += 1
        return ConnectedTerminalResult(False, reason, (f"ERROR {reason}",))


__all__ = [
    "MAX_TERMINAL_LINE_BYTES",
    "TerminalMode",
    "ConnectedTerminalSnapshot",
    "ConnectedTerminalResult",
    "ConnectedTerminalSession",
]
