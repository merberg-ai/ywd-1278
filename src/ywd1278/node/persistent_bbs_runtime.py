"""0I-P4 single-owner connected persistent BBS runtime; host composition only.

This module dynamically accepts one inbound direct AX.25 connected-mode peer,
reuses the frozen 0H-P5 inbound coordinator and frozen 0G timed link, and adapts
the frozen 0I-P2 classic BBS personality over the frozen 0I-P1 persistent
mailbox store.  Returned AX.25 actions remain inert: this layer owns no modem,
KISS socket, UART, CSMA loop, thread, service lifecycle, or RF path.
"""
from __future__ import annotations

from dataclasses import dataclass

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import DataLinkAction
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame
from ywd1278.link.timed_link import LinkTimerConfig
from ywd1278.node.classic_bbs import ClassicBBSSession
from ywd1278.node.inbound import InboundNodeSession
from ywd1278.node.persistent_mailbox import PersistentMailboxStore


DEFAULT_CONNECTED_MAXFRAME = 1
DEFAULT_CONNECTED_RECEIVE_PACLEN = 256
DEFAULT_CONNECTED_TIMERS = LinkTimerConfig(
    t1_seconds=35.0,
    t2_seconds=1.0,
    t3_seconds=180.0,
    max_retries=2,
)


@dataclass(frozen=True)
class PersistentBBSRuntimeSnapshot:
    local: str
    active_peer: str | None
    state: LinkState
    sessions_accepted: int
    busy_rejections: int
    frames_received: int
    actions_prepared: int
    commands: int
    close_requested: bool


@dataclass(frozen=True)
class PersistentBBSRuntimeResult:
    accepted: bool
    reason: str
    actions: tuple[DataLinkAction, ...] = ()


@dataclass(frozen=True)
class _AdapterSnapshot:
    commands: int
    close_requested: bool


@dataclass(frozen=True)
class _AdapterResult:
    responses: tuple[bytes, ...]
    close_requested: bool


class _ClassicBBSCommandAdapter:
    """Make frozen P2 look like the frozen P5 command-session protocol."""

    def __init__(
        self,
        *,
        local: Address,
        peer: Address,
        alias: str,
        store: PersistentMailboxStore,
        paclen: int,
        now_ns,
        info: str,
    ) -> None:  # type: ignore[no-untyped-def]
        self._local = Address(local.callsign, local.ssid)
        self._alias = str(alias).strip().upper()
        self._bbs = ClassicBBSSession(
            local=local,
            peer=peer,
            store=store,
            paclen=paclen,
            now_ns=now_ns,
            info=info,
        )

    @property
    def snapshot(self) -> _AdapterSnapshot:
        snap = self._bbs.snapshot
        return _AdapterSnapshot(snap.commands, snap.close_requested)

    def banner(self) -> tuple[bytes, ...]:
        connected = f"{self._alias}:{self._local}}} Connected to BBS\r".encode("ascii")
        return (connected,) + tuple(action.data for action in self._bbs.banner())

    def feed(self, information: bytes) -> _AdapterResult:
        result = self._bbs.feed(information)
        return _AdapterResult(
            tuple(action.data for action in result.actions),
            result.close_requested,
        )


class PersistentBBSRuntime:
    """Accept at most one direct inbound connected BBS owner at a time."""

    def __init__(
        self,
        *,
        local: Address,
        alias: str,
        store: PersistentMailboxStore,
        mailbox_paclen: int,
        now_ns,
        info: str,
        timers: LinkTimerConfig = DEFAULT_CONNECTED_TIMERS,
    ) -> None:  # type: ignore[no-untyped-def]
        if not isinstance(local, Address):
            raise TypeError("local must be an AX.25 Address")
        if not isinstance(store, PersistentMailboxStore):
            raise TypeError("store must be PersistentMailboxStore")
        normalized_alias = str(alias).strip().upper()
        if not 1 <= len(normalized_alias) <= 6 or not normalized_alias.isascii() or not normalized_alias.isalnum():
            raise ValueError("alias must be 1..6 alphanumeric ASCII characters")
        if isinstance(mailbox_paclen, bool) or not isinstance(mailbox_paclen, int) or not 32 <= mailbox_paclen <= 256:
            raise ValueError("mailbox_paclen must be 32..256")
        if not callable(now_ns):
            raise TypeError("now_ns must be callable")
        if not isinstance(timers, LinkTimerConfig):
            raise TypeError("timers must be LinkTimerConfig")
        self._local = Address(local.callsign, local.ssid)
        self._alias = normalized_alias
        self._store = store
        self._mailbox_paclen = mailbox_paclen
        self._now_ns = now_ns
        self._info = info
        self._timers = timers
        self._active: InboundNodeSession | None = None
        self._peer: Address | None = None
        self._sessions_accepted = 0
        self._busy_rejections = 0
        self._frames_received = 0
        self._actions_prepared = 0
        self._last_commands = 0
        self._last_close_requested = False

    @property
    def snapshot(self) -> PersistentBBSRuntimeSnapshot:
        state = LinkState.DISCONNECTED
        commands = self._last_commands
        close_requested = self._last_close_requested
        if self._active is not None:
            snap = self._active.snapshot
            state = snap.state
            commands = snap.commands
            close_requested = snap.bye_seen or snap.orderly_release_started
        return PersistentBBSRuntimeSnapshot(
            local=str(self._local),
            active_peer=None if self._peer is None else str(self._peer),
            state=state,
            sessions_accepted=self._sessions_accepted,
            busy_rejections=self._busy_rejections,
            frames_received=self._frames_received,
            actions_prepared=self._actions_prepared,
            commands=commands,
            close_requested=close_requested,
        )

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> PersistentBBSRuntimeResult:
        try:
            parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
        except (TypeError, ValueError) as exc:
            return PersistentBBSRuntimeResult(False, f"malformed AX.25 frame: {exc}")
        self._frames_received += 1
        source = parsed["source"]
        destination = parsed["destination"]
        if not isinstance(source, Address) or not isinstance(destination, Address):
            return PersistentBBSRuntimeResult(False, "parsed frame has invalid addresses")
        if (destination.callsign, destination.ssid) != (self._local.callsign, self._local.ssid):
            return PersistentBBSRuntimeResult(False, "frame is not addressed to this BBS")
        if parsed["path"]:
            return PersistentBBSRuntimeResult(False, "connected BBS requires a direct AX.25 link")

        if self._active is None:
            if parsed["frame_type"] != "SABM":
                return PersistentBBSRuntimeResult(False, "no active session; SABM required")
            self._start_peer(Address(source.callsign, source.ssid))
        elif self._peer is None:
            raise RuntimeError("active persistent BBS session lost peer identity")
        elif (source.callsign, source.ssid) != (self._peer.callsign, self._peer.ssid):
            if parsed["frame_type"] == "SABM":
                self._busy_rejections += 1
                dm = DataLinkAction(
                    "DM",
                    build_unnumbered_frame(
                        source=self._local,
                        destination=Address(source.callsign, source.ssid),
                        frame_type="DM",
                        command=False,
                        poll_final=bool(parsed["poll_final"]),
                    ),
                )
                self._actions_prepared += 1
                return PersistentBBSRuntimeResult(
                    False,
                    f"BBS busy with {self._peer}; contender rejected with DM",
                    (dm,),
                )
            return PersistentBBSRuntimeResult(False, f"BBS owned by {self._peer}")

        assert self._active is not None
        result = self._active.handle_frame(frame_no_fcs, now=now)
        self._actions_prepared += len(result.actions)
        self._capture_and_release_if_disconnected()
        return PersistentBBSRuntimeResult(result.accepted, result.reason, result.actions)

    def poll(self, *, now: float) -> PersistentBBSRuntimeResult:
        if self._active is None:
            return PersistentBBSRuntimeResult(True, "persistent BBS idle")
        result = self._active.poll(now=now)
        self._actions_prepared += len(result.actions)
        self._capture_and_release_if_disconnected()
        return PersistentBBSRuntimeResult(result.accepted, result.reason, result.actions)

    def _start_peer(self, peer: Address) -> None:
        peer = Address(peer.callsign, peer.ssid)

        def factory() -> _ClassicBBSCommandAdapter:
            return _ClassicBBSCommandAdapter(
                local=self._local,
                peer=peer,
                alias=self._alias,
                store=self._store,
                paclen=self._mailbox_paclen,
                now_ns=self._now_ns,
                info=self._info,
            )

        self._active = InboundNodeSession(
            local=self._local,
            remote=peer,
            alias=self._alias,
            maxframe=DEFAULT_CONNECTED_MAXFRAME,
            paclen=DEFAULT_CONNECTED_RECEIVE_PACLEN,
            timers=self._timers,
            session_factory=factory,
        )
        self._peer = peer
        self._sessions_accepted += 1
        self._last_commands = 0
        self._last_close_requested = False

    def _capture_and_release_if_disconnected(self) -> None:
        if self._active is None:
            return
        snap = self._active.snapshot
        if snap.state is not LinkState.DISCONNECTED:
            return
        self._last_commands = snap.commands
        self._last_close_requested = snap.bye_seen or snap.orderly_release_started
        self._active = None
        self._peer = None


__all__ = [
    "DEFAULT_CONNECTED_MAXFRAME",
    "DEFAULT_CONNECTED_RECEIVE_PACLEN",
    "DEFAULT_CONNECTED_TIMERS",
    "PersistentBBSRuntimeSnapshot",
    "PersistentBBSRuntimeResult",
    "PersistentBBSRuntime",
]
