"""0G-P1 deterministic modulo-8 AX.25 link establishment/release state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ywd1278.ax25 import Address, append_fcs, encode_address, parse_frame


U_CONTROL = {
    "DM": 0x0F,
    "SABM": 0x2F,
    "DISC": 0x43,
    "UA": 0x63,
}


def sequence_next(value: int) -> int:
    """Return the next valid modulo-8 sequence number."""

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7:
        raise ValueError("sequence number must be an integer 0..7")
    return (value + 1) & 0x07


def sequence_distance(start: int, end: int) -> int:
    """Return the forward modulo-8 distance from *start* to *end*."""

    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7 for value in (start, end)):
        raise ValueError("sequence numbers must be integers 0..7")
    return (end - start) & 0x07


class LinkState(Enum):
    DISCONNECTED = "DISCONNECTED"
    AWAITING_CONNECTION = "AWAITING_CONNECTION"
    CONNECTED = "CONNECTED"
    AWAITING_RELEASE = "AWAITING_RELEASE"


@dataclass(frozen=True)
class LinkAction:
    frame_type: str
    command: bool
    poll_final: bool
    frame_no_fcs: bytes


@dataclass(frozen=True)
class LinkSnapshot:
    state: LinkState
    local: str
    remote: str
    vs: int
    vr: int
    va: int
    transitions: int
    received_frames: int
    emitted_frames: int


@dataclass(frozen=True)
class LinkEventResult:
    accepted: bool
    reason: str
    before: LinkState
    after: LinkState
    actions: tuple[LinkAction, ...] = ()


def build_unnumbered_frame(
    *,
    source: Address,
    destination: Address,
    frame_type: str,
    command: bool,
    poll_final: bool,
    include_fcs: bool = False,
) -> bytes:
    """Build one direct SABM/UA/DISC/DM frame with conventional C bits."""

    if not isinstance(source, Address) or not isinstance(destination, Address):
        raise TypeError("source and destination must be Address values")
    name = str(frame_type).upper()
    if name not in U_CONTROL:
        raise ValueError("frame_type must be SABM, UA, DISC, or DM")
    if not isinstance(command, bool) or not isinstance(poll_final, bool):
        raise TypeError("command and poll_final must be bool")
    dest = Address(destination.callsign, destination.ssid, command)
    src = Address(source.callsign, source.ssid, not command)
    body = (
        encode_address(dest, last=False)
        + encode_address(src, last=True)
        + bytes((U_CONTROL[name] | (0x10 if poll_final else 0),))
    )
    return append_fcs(body) if include_fcs else body


class Modulo8Link:
    """Pure caller-driven P1 link setup/release state machine.

    P1 owns no timers, retry policy, I/S-frame handling, queue, thread, console,
    modem, or RF path. Returned actions are inert AX.25 frame bodies.
    """

    def __init__(self, *, local: Address, remote: Address) -> None:
        if not isinstance(local, Address) or not isinstance(remote, Address):
            raise TypeError("local and remote must be Address values")
        if local.callsign == remote.callsign and local.ssid == remote.ssid:
            raise ValueError("local and remote station addresses must differ")
        self._local = Address(local.callsign, local.ssid)
        self._remote = Address(remote.callsign, remote.ssid)
        self._state = LinkState.DISCONNECTED
        self._vs = 0
        self._vr = 0
        self._va = 0
        self._transitions = 0
        self._received_frames = 0
        self._emitted_frames = 0

    @property
    def snapshot(self) -> LinkSnapshot:
        return LinkSnapshot(
            state=self._state,
            local=str(self._local),
            remote=str(self._remote),
            vs=self._vs,
            vr=self._vr,
            va=self._va,
            transitions=self._transitions,
            received_frames=self._received_frames,
            emitted_frames=self._emitted_frames,
        )

    def connect(self) -> LinkEventResult:
        before = self._state
        if before is not LinkState.DISCONNECTED:
            return LinkEventResult(False, "connect requires DISCONNECTED", before, before)
        self._reset_sequence_state()
        self._set_state(LinkState.AWAITING_CONNECTION)
        action = self._action("SABM", command=True, poll_final=True)
        return LinkEventResult(True, "SABM command prepared", before, self._state, (action,))

    def disconnect(self) -> LinkEventResult:
        before = self._state
        if before is LinkState.AWAITING_CONNECTION:
            self._set_state(LinkState.DISCONNECTED)
            return LinkEventResult(True, "pending connection cancelled", before, self._state)
        if before is not LinkState.CONNECTED:
            return LinkEventResult(False, "disconnect requires CONNECTED", before, before)
        self._set_state(LinkState.AWAITING_RELEASE)
        action = self._action("DISC", command=True, poll_final=True)
        return LinkEventResult(True, "DISC command prepared", before, self._state, (action,))

    def handle_frame(self, frame_no_fcs: bytes) -> LinkEventResult:
        """Consume one direct, correctly addressed U frame without an FCS."""

        before = self._state
        try:
            parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
        except (TypeError, ValueError) as exc:
            return LinkEventResult(False, f"malformed frame: {exc}", before, before)
        if parsed["frame_class"] != "U" or parsed["frame_type"] not in U_CONTROL:
            return LinkEventResult(False, "P1 handles SABM/UA/DISC/DM only", before, before)
        if parsed["info"]:
            return LinkEventResult(False, "P1 control frames must not contain information", before, before)
        if parsed["path"]:
            return LinkEventResult(False, "P1 connected links are direct only", before, before)
        destination = parsed["destination"]
        source = parsed["source"]
        if self._identity(destination) != self._identity(self._local):
            return LinkEventResult(False, "frame is not addressed to local station", before, before)
        if self._identity(source) != self._identity(self._remote):
            return LinkEventResult(False, "frame source is not the configured remote", before, before)
        if destination.flag == source.flag:
            return LinkEventResult(False, "invalid AX.25 command/response bits", before, before)
        is_command = bool(destination.flag and not source.flag)
        name = str(parsed["frame_type"])
        if name in ("SABM", "DISC") and not is_command:
            return LinkEventResult(False, f"{name} must be a command", before, before)
        if name in ("UA", "DM") and is_command:
            return LinkEventResult(False, f"{name} must be a response", before, before)

        self._received_frames += 1
        poll_final = bool(parsed["poll_final"])
        if name == "SABM":
            self._reset_sequence_state()
            self._set_state(LinkState.CONNECTED)
            action = self._action("UA", command=False, poll_final=poll_final)
            return LinkEventResult(True, "remote SABM accepted", before, self._state, (action,))
        if name == "DISC":
            self._reset_sequence_state()
            if before is LinkState.DISCONNECTED:
                action = self._action("DM", command=False, poll_final=poll_final)
                return LinkEventResult(True, "already disconnected", before, before, (action,))
            self._set_state(LinkState.DISCONNECTED)
            action = self._action("UA", command=False, poll_final=poll_final)
            return LinkEventResult(True, "remote DISC accepted", before, self._state, (action,))
        if name == "UA":
            if not poll_final:
                return LinkEventResult(False, "UA response requires final bit", before, before)
            if before is LinkState.AWAITING_CONNECTION:
                self._reset_sequence_state()
                self._set_state(LinkState.CONNECTED)
                return LinkEventResult(True, "connection established", before, self._state)
            if before is LinkState.AWAITING_RELEASE:
                self._reset_sequence_state()
                self._set_state(LinkState.DISCONNECTED)
                return LinkEventResult(True, "release confirmed", before, self._state)
            return LinkEventResult(False, "unexpected UA response", before, before)

        # A valid DM always proves that no link currently exists at the peer.
        self._reset_sequence_state()
        if before is not LinkState.DISCONNECTED:
            self._set_state(LinkState.DISCONNECTED)
        return LinkEventResult(True, "remote reports disconnected mode", before, self._state)

    def _action(self, frame_type: str, *, command: bool, poll_final: bool) -> LinkAction:
        frame = build_unnumbered_frame(
            source=self._local,
            destination=self._remote,
            frame_type=frame_type,
            command=command,
            poll_final=poll_final,
            include_fcs=False,
        )
        self._emitted_frames += 1
        return LinkAction(frame_type, command, poll_final, frame)

    def _set_state(self, state: LinkState) -> None:
        if state is not self._state:
            self._state = state
            self._transitions += 1

    def _reset_sequence_state(self) -> None:
        self._vs = self._vr = self._va = 0

    @staticmethod
    def _identity(address: Address) -> tuple[str, int]:
        return address.callsign, address.ssid


__all__ = [
    "LinkAction",
    "LinkEventResult",
    "LinkSnapshot",
    "LinkState",
    "Modulo8Link",
    "build_unnumbered_frame",
    "sequence_distance",
    "sequence_next",
]
