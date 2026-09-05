"""0G-P5 bounded multi-session ownership above the frozen P4 terminal."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ywd1278.ax25 import Address
from ywd1278.link.modulo8 import LinkState
from ywd1278.link.terminal_session import (
    ConnectedTerminalResult,
    ConnectedTerminalSession,
    TerminalMode,
)
from ywd1278.link.timed_link import LinkTimerConfig


MAX_CONNECTED_TERMINAL_SESSIONS = 8
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}\Z")


@dataclass(frozen=True)
class SessionManagerSnapshot:
    session_ids: tuple[str, ...]
    session_count: int
    max_sessions: int
    owner_session_id: str | None
    pending_close_session_id: str | None
    ownership_generation: int
    contention_rejections: int


@dataclass(frozen=True)
class ManagedSessionResult:
    accepted: bool
    reason: str
    session_id: str | None = None
    terminal: ConnectedTerminalResult | None = None


class ConnectedSessionManager:
    """Own bounded P4 sessions and grant one exclusive connected-link lease."""

    def __init__(
        self,
        *,
        local: Address,
        max_sessions: int = 4,
        maxframe: int = 4,
        paclen: int = 128,
        timers: LinkTimerConfig = LinkTimerConfig(),
    ) -> None:
        if not isinstance(local, Address):
            raise TypeError("local must be an AX.25 Address")
        if (
            isinstance(max_sessions, bool)
            or not isinstance(max_sessions, int)
            or not 1 <= max_sessions <= MAX_CONNECTED_TERMINAL_SESSIONS
        ):
            raise ValueError(
                f"max_sessions must be an integer 1..{MAX_CONNECTED_TERMINAL_SESSIONS}"
            )
        self._local = Address(local.callsign, local.ssid)
        self._max_sessions = max_sessions
        self._maxframe = maxframe
        self._paclen = paclen
        self._timers = timers
        # Validate shared link policy before any session can be registered.
        ConnectedTerminalSession(
            local=self._local, maxframe=maxframe, paclen=paclen, timers=timers
        )
        self._sessions: dict[str, ConnectedTerminalSession] = {}
        self._owner: str | None = None
        self._pending_close: str | None = None
        self._ownership_generation = 0
        self._contention_rejections = 0

    @property
    def snapshot(self) -> SessionManagerSnapshot:
        return SessionManagerSnapshot(
            session_ids=tuple(self._sessions),
            session_count=len(self._sessions),
            max_sessions=self._max_sessions,
            owner_session_id=self._owner,
            pending_close_session_id=self._pending_close,
            ownership_generation=self._ownership_generation,
            contention_rejections=self._contention_rejections,
        )

    def open_session(self, session_id: str) -> ManagedSessionResult:
        validation = self._validate_session_id(session_id)
        if validation is not None:
            return ManagedSessionResult(False, validation)
        if session_id in self._sessions:
            return ManagedSessionResult(False, "session id already exists", session_id)
        if len(self._sessions) >= self._max_sessions:
            return ManagedSessionResult(False, "session limit reached", session_id)
        self._sessions[session_id] = ConnectedTerminalSession(
            local=self._local,
            maxframe=self._maxframe,
            paclen=self._paclen,
            timers=self._timers,
        )
        return ManagedSessionResult(True, "session opened", session_id)

    def close_session(self, session_id: str, *, now: float) -> ManagedSessionResult:
        session = self._sessions.get(session_id)
        if session is None:
            return ManagedSessionResult(False, "unknown session", session_id)
        if session_id != self._owner:
            del self._sessions[session_id]
            return ManagedSessionResult(True, "idle session closed", session_id)
        state = session.snapshot.link_state
        if state is LinkState.DISCONNECTED:
            self._release_owner(session_id)
            del self._sessions[session_id]
            return ManagedSessionResult(True, "owner session closed", session_id)
        self._pending_close = session_id
        if session.snapshot.mode is TerminalMode.CONNECTED:
            session.execute_line("COMMAND", now=now)
        release = session.execute_line("DISCONNECT", now=now)
        if session.snapshot.link_state is LinkState.DISCONNECTED:
            self._finish_pending_close()
        return ManagedSessionResult(release.accepted, "owner close awaiting release", session_id, release)

    def execute_line(
        self, session_id: str, line: str, *, now: float
    ) -> ManagedSessionResult:
        session = self._sessions.get(session_id)
        if session is None:
            return ManagedSessionResult(False, "unknown session", session_id)
        if self._pending_close == session_id:
            return ManagedSessionResult(False, "session close is pending", session_id)
        is_connect = self._is_connect_command(line)
        if is_connect and self._owner not in (None, session_id):
            self._contention_rejections += 1
            return ManagedSessionResult(
                False, f"connected link owned by session {self._owner}", session_id
            )
        claimed = False
        if is_connect and self._owner is None:
            self._owner = session_id
            self._ownership_generation += 1
            claimed = True
        terminal = session.execute_line(line, now=now)
        if claimed and not terminal.accepted:
            self._release_owner(session_id)
        self._release_if_disconnected(session_id)
        return ManagedSessionResult(terminal.accepted, terminal.reason, session_id, terminal)

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> ManagedSessionResult:
        if self._owner is None:
            return ManagedSessionResult(False, "no connected-link owner")
        session_id = self._owner
        terminal = self._sessions[session_id].handle_frame(frame_no_fcs, now=now)
        self._release_if_disconnected(session_id)
        return ManagedSessionResult(terminal.accepted, terminal.reason, session_id, terminal)

    def poll(self, *, now: float) -> ManagedSessionResult:
        if self._owner is None:
            return ManagedSessionResult(True, "no connected-link owner")
        session_id = self._owner
        terminal = self._sessions[session_id].poll(now=now)
        self._release_if_disconnected(session_id)
        return ManagedSessionResult(terminal.accepted, terminal.reason, session_id, terminal)

    def session_snapshot(self, session_id: str):
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session.snapshot

    def _release_if_disconnected(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None or session.snapshot.link_state is not LinkState.DISCONNECTED:
            return
        self._release_owner(session_id)
        if self._pending_close == session_id:
            self._finish_pending_close()

    def _release_owner(self, session_id: str) -> None:
        if self._owner == session_id:
            self._owner = None
            self._ownership_generation += 1

    def _finish_pending_close(self) -> None:
        session_id = self._pending_close
        if session_id is None:
            return
        self._release_owner(session_id)
        self._sessions.pop(session_id, None)
        self._pending_close = None

    @staticmethod
    def _is_connect_command(line: str) -> bool:
        if not isinstance(line, str) or "\x00" in line:
            return False
        parts = line.strip(" \t\r\n").split()
        return bool(parts and parts[0].upper() == "CONNECT")

    @staticmethod
    def _validate_session_id(session_id: str) -> str | None:
        if not isinstance(session_id, str):
            return "session id must be str"
        if _SESSION_ID.fullmatch(session_id) is None:
            return "session id must be 1..32 safe ASCII characters"
        return None


__all__ = [
    "MAX_CONNECTED_TERMINAL_SESSIONS",
    "SessionManagerSnapshot",
    "ManagedSessionResult",
    "ConnectedSessionManager",
]
