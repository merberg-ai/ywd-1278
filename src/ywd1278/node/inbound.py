"""0H-P5 bounded inbound node session coordinator with inert frame actions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import DataLinkAction
from ywd1278.link.modulo8 import LinkState
from ywd1278.link.timed_link import LinkTimerConfig, TimedModulo8DataLink
from ywd1278.node.commands import NodeCommandSession


MAX_PENDING_RESPONSES = 16
MAX_PENDING_RESPONSE_BYTES = 2048


@dataclass(frozen=True)
class InboundNodeSnapshot:
    local: str
    remote: str
    state: LinkState
    pending_responses: int
    pending_response_bytes: int
    connections: int
    commands: int
    help_seen: bool
    info_seen: bool
    bye_seen: bool
    orderly_release_started: bool


@dataclass(frozen=True)
class InboundNodeResult:
    accepted: bool
    reason: str
    actions: tuple[DataLinkAction, ...] = ()


class InboundNodeSession:
    """Compose the frozen P1 command session and P3 timed data link.

    Returned actions are deliberately inert.  The owning runtime decides whether
    and where to dispatch them.
    """

    def __init__(
        self, *, local: Address, remote: Address, alias: str = "YWDNOD",
        maxframe: int = 4, paclen: int = 128,
        timers: LinkTimerConfig = LinkTimerConfig(),
        session_factory: Callable[[], CommandSession] | None = None,
    ) -> None:
        if not isinstance(local, Address) or not isinstance(remote, Address):
            raise TypeError("local and remote must be AX.25 Address values")
        self._local = Address(local.callsign, local.ssid)
        self._remote = Address(remote.callsign, remote.ssid)
        self._alias = alias
        self._link = TimedModulo8DataLink(
            local=self._local, remote=self._remote, maxframe=maxframe,
            paclen=paclen, timers=timers,
        )
        self._session_factory = session_factory or (
            lambda: NodeCommandSession(callsign=self._local, alias=self._alias)
        )
        self._node = self._session_factory()
        self._pending: deque[bytes] = deque()
        self._pending_bytes = 0
        self._connections = 0
        self._help_seen = self._info_seen = self._bye_seen = False
        self._release_started = False

    @property
    def snapshot(self) -> InboundNodeSnapshot:
        return InboundNodeSnapshot(
            local=str(self._local), remote=str(self._remote),
            state=self._link.snapshot.link.state,
            pending_responses=len(self._pending),
            pending_response_bytes=self._pending_bytes,
            connections=self._connections,
            commands=self._node.snapshot.commands,
            help_seen=self._help_seen, info_seen=self._info_seen,
            bye_seen=self._bye_seen,
            orderly_release_started=self._release_started,
        )

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> InboundNodeResult:
        try:
            parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
        except (TypeError, ValueError):
            parsed = None
        before = self._link.snapshot.link.state
        handled = self._link.handle_frame(frame_no_fcs, now=now)
        if not handled.accepted:
            return InboundNodeResult(False, handled.reason)
        actions = list(handled.actions)

        if parsed is not None and parsed["frame_type"] == "SABM":
            self._node = self._session_factory()
            self._pending.clear()
            self._pending_bytes = 0
            self._help_seen = self._info_seen = self._bye_seen = False
            self._release_started = False
            if before is LinkState.DISCONNECTED:
                self._connections += 1
            if not self._enqueue(self._node.banner()):
                return self._fail_closed("node banner exceeded response queue", actions, now)

        for information in handled.delivered:
            response = self._node.feed(information)
            self._observe_command_response(response.responses, response.close_requested)
            if not self._enqueue(response.responses):
                return self._fail_closed("node response queue limit exceeded", actions, now)

        actions.extend(self._flush(now=now))
        actions.extend(self._release_if_ready(now=now))
        return InboundNodeResult(True, handled.reason, tuple(actions))

    def poll(self, *, now: float) -> InboundNodeResult:
        polled = self._link.poll(now=now)
        actions = list(polled.actions)
        actions.extend(self._flush(now=now))
        actions.extend(self._release_if_ready(now=now))
        return InboundNodeResult(polled.accepted, polled.reason, tuple(actions))

    def _enqueue(self, responses: tuple[bytes, ...]) -> bool:
        added_bytes = sum(len(item) for item in responses)
        if len(self._pending) + len(responses) > MAX_PENDING_RESPONSES:
            return False
        if self._pending_bytes + added_bytes > MAX_PENDING_RESPONSE_BYTES:
            return False
        self._pending.extend(responses)
        self._pending_bytes += added_bytes
        return True

    def _fail_closed(
        self, reason: str, actions: list[DataLinkAction], now: float,
    ) -> InboundNodeResult:
        self._pending.clear()
        self._pending_bytes = 0
        if self._link.snapshot.link.state is LinkState.CONNECTED:
            actions.extend(self._link.disconnect(now=now).actions)
            self._release_started = True
        return InboundNodeResult(False, reason, tuple(actions))

    def _flush(self, *, now: float) -> tuple[DataLinkAction, ...]:
        actions: list[DataLinkAction] = []
        while self._pending and self._link.snapshot.link.state is LinkState.CONNECTED:
            sent = self._link.send_information(self._pending[0], now=now)
            if not sent.accepted:
                break
            item = self._pending.popleft()
            self._pending_bytes -= len(item)
            actions.extend(sent.actions)
        return tuple(actions)

    def _release_if_ready(self, *, now: float) -> tuple[DataLinkAction, ...]:
        if (
            self._node.snapshot.close_requested and not self._pending
            and self._link.snapshot.link.outstanding == 0
            and self._link.snapshot.link.state is LinkState.CONNECTED
        ):
            released = self._link.disconnect(now=now)
            if released.accepted:
                self._release_started = True
                return released.actions
        return ()

    def _observe_command_response(
        self, responses: tuple[bytes, ...], close_requested: bool,
    ) -> None:
        if any(item.startswith(b"HELP ") for item in responses):
            self._help_seen = True
        if any(item.startswith(b"NODE ") for item in responses):
            self._info_seen = True
        if close_requested and responses == (b"BYE\r",):
            self._bye_seen = True


__all__ = [
    "MAX_PENDING_RESPONSES", "MAX_PENDING_RESPONSE_BYTES",
    "InboundNodeSnapshot", "InboundNodeResult", "InboundNodeSession",
]
class CommandSession(Protocol):
    @property
    def snapshot(self): ...  # type: ignore[no-untyped-def]
    def banner(self) -> tuple[bytes, ...]: ...
    def feed(self, information: bytes): ...  # type: ignore[no-untyped-def]
