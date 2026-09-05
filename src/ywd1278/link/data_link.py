"""0G-P2 bounded modulo-8 I-frame and supervisory sequencing."""

from __future__ import annotations

from dataclasses import dataclass

from ywd1278.ax25 import AX25_PID_NO_L3, Address, append_fcs, encode_address, parse_frame
from ywd1278.link.modulo8 import LinkEventResult, LinkState, Modulo8Link, sequence_next


S_CONTROL = {"RR": 0x01, "RNR": 0x05, "REJ": 0x09}


@dataclass(frozen=True)
class DataLinkAction:
    frame_type: str
    frame_no_fcs: bytes
    retransmission: bool = False


@dataclass(frozen=True)
class DataLinkSnapshot:
    state: LinkState
    local: str
    remote: str
    vs: int
    vr: int
    va: int
    outstanding: int
    maxframe: int
    paclen: int
    local_busy: bool
    remote_busy: bool
    delivered_frames: int
    rejected_frames: int


@dataclass(frozen=True)
class DataLinkResult:
    accepted: bool
    reason: str
    actions: tuple[DataLinkAction, ...] = ()
    delivered: tuple[bytes, ...] = ()


def _address_bytes(*, source: Address, destination: Address, command: bool) -> bytes:
    dest = Address(destination.callsign, destination.ssid, command)
    src = Address(source.callsign, source.ssid, not command)
    return encode_address(dest, last=False) + encode_address(src, last=True)


def build_i_frame(
    *, source: Address, destination: Address, ns: int, nr: int, info: bytes,
    poll_final: bool = False, command: bool = True, include_fcs: bool = False,
) -> bytes:
    """Build one direct modulo-8 I frame."""

    _validate_sequence(ns)
    _validate_sequence(nr)
    if not isinstance(info, bytes):
        raise TypeError("info must be bytes")
    control = (ns << 1) | (0x10 if poll_final else 0) | (nr << 5)
    body = _address_bytes(source=source, destination=destination, command=command)
    body += bytes((control, AX25_PID_NO_L3)) + info
    return append_fcs(body) if include_fcs else body


def build_s_frame(
    *, source: Address, destination: Address, frame_type: str, nr: int,
    poll_final: bool = False, command: bool = False, include_fcs: bool = False,
) -> bytes:
    """Build one direct modulo-8 RR, RNR, or REJ frame."""

    _validate_sequence(nr)
    name = str(frame_type).upper()
    if name not in S_CONTROL:
        raise ValueError("frame_type must be RR, RNR, or REJ")
    control = S_CONTROL[name] | (0x10 if poll_final else 0) | (nr << 5)
    body = _address_bytes(source=source, destination=destination, command=command)
    body += bytes((control,))
    return append_fcs(body) if include_fcs else body


class Modulo8DataLink:
    """P1 link state plus bounded, caller-driven P2 data sequencing."""

    def __init__(
        self, *, local: Address, remote: Address, maxframe: int = 4, paclen: int = 128,
    ) -> None:
        if isinstance(maxframe, bool) or not isinstance(maxframe, int) or not 1 <= maxframe <= 7:
            raise ValueError("maxframe must be an integer 1..7")
        if isinstance(paclen, bool) or not isinstance(paclen, int) or not 1 <= paclen <= 256:
            raise ValueError("paclen must be an integer 1..256")
        self._link = Modulo8Link(local=local, remote=remote)
        self._local = Address(local.callsign, local.ssid)
        self._remote = Address(remote.callsign, remote.ssid)
        self._maxframe = maxframe
        self._paclen = paclen
        self._vs = self._vr = self._va = 0
        self._outstanding: list[tuple[int, bytes]] = []
        self._local_busy = False
        self._remote_busy = False
        self._delivered_frames = 0
        self._rejected_frames = 0

    @property
    def snapshot(self) -> DataLinkSnapshot:
        return DataLinkSnapshot(
            state=self._link.snapshot.state, local=str(self._local), remote=str(self._remote),
            vs=self._vs, vr=self._vr, va=self._va, outstanding=len(self._outstanding),
            maxframe=self._maxframe, paclen=self._paclen, local_busy=self._local_busy,
            remote_busy=self._remote_busy, delivered_frames=self._delivered_frames,
            rejected_frames=self._rejected_frames,
        )

    def connect(self) -> LinkEventResult:
        result = self._link.connect()
        if result.accepted:
            self._reset_data_state()
        return result

    def disconnect(self) -> LinkEventResult:
        result = self._link.disconnect()
        if result.accepted and result.after is LinkState.DISCONNECTED:
            self._reset_data_state()
        return result

    def send_information(self, info: bytes) -> DataLinkResult:
        if not isinstance(info, bytes):
            raise TypeError("info must be bytes")
        if self.snapshot.state is not LinkState.CONNECTED:
            return self._reject("information requires CONNECTED")
        if not info:
            return self._reject("information must not be empty")
        if len(info) > self._paclen:
            return self._reject(f"information exceeds PACLEN {self._paclen}")
        if self._remote_busy:
            return self._reject("remote receiver is busy")
        if len(self._outstanding) >= self._maxframe:
            return self._reject("MAXFRAME window is full")
        sequence = self._vs
        frame = build_i_frame(
            source=self._local, destination=self._remote, ns=sequence, nr=self._vr,
            info=info, command=True,
        )
        self._outstanding.append((sequence, frame))
        self._vs = sequence_next(self._vs)
        return DataLinkResult(True, f"I frame N(S)={sequence} prepared", (DataLinkAction("I", frame),))

    def set_local_busy(self, busy: bool) -> DataLinkResult:
        if not isinstance(busy, bool):
            raise TypeError("busy must be bool")
        if self.snapshot.state is not LinkState.CONNECTED:
            return self._reject("receiver state requires CONNECTED")
        if busy == self._local_busy:
            return DataLinkResult(True, "receiver state unchanged")
        self._local_busy = busy
        name = "RNR" if busy else "RR"
        return DataLinkResult(True, f"local receiver {'busy' if busy else 'ready'}", (self._s_action(name),))

    def handle_frame(self, frame_no_fcs: bytes) -> DataLinkResult:
        try:
            parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
        except (TypeError, ValueError) as exc:
            return self._reject(f"malformed frame: {exc}")
        if parsed["frame_class"] == "U":
            before = self._link.snapshot.state
            result = self._link.handle_frame(frame_no_fcs)
            if result.accepted and (
                result.after is not before or parsed["frame_type"] in ("SABM", "DISC", "DM")
            ):
                self._reset_data_state()
            actions = tuple(DataLinkAction(item.frame_type, item.frame_no_fcs) for item in result.actions)
            if not result.accepted:
                self._rejected_frames += 1
            return DataLinkResult(result.accepted, result.reason, actions)
        validation = self._validate_incoming(parsed)
        if validation is not None:
            return self._reject(validation)
        if self.snapshot.state is not LinkState.CONNECTED:
            return self._reject("I/S frame received while disconnected")
        if parsed["frame_class"] == "S":
            if parsed["info"]:
                return self._reject("supervisory frame must not contain information")
            if parsed["frame_type"] not in S_CONTROL:
                return self._reject("P2 does not support SREJ")
        else:
            if parsed["pid"] != AX25_PID_NO_L3:
                return self._reject("P2 supports PID F0 only")
            if len(parsed["info"]) > self._paclen:
                return self._reject(f"received information exceeds PACLEN {self._paclen}")
        nr = int(parsed["nr"])
        ack_count = self._ack_count(nr)
        if ack_count is None:
            return self._reject(f"invalid N(R)={nr} for V(A)={self._va} V(S)={self._vs}")
        self._apply_ack(nr, ack_count)

        if parsed["frame_class"] == "S":
            return self._handle_supervisory(parsed)
        ns = int(parsed["ns"])
        if self._local_busy:
            return DataLinkResult(
                True, "local receiver busy; I frame not accepted",
                (self._s_action("RNR", poll_final=bool(parsed["poll_final"])),),
            )
        if ns != self._vr:
            return DataLinkResult(
                True, f"unexpected N(S)={ns}; REJ requests {self._vr}",
                (self._s_action("REJ", poll_final=bool(parsed["poll_final"])),),
            )
        info = bytes(parsed["info"])
        self._vr = sequence_next(self._vr)
        self._delivered_frames += 1
        return DataLinkResult(
            True, f"I frame N(S)={ns} delivered",
            (self._s_action("RR", poll_final=bool(parsed["poll_final"])),), (info,),
        )

    def _handle_supervisory(self, parsed: dict) -> DataLinkResult:
        name = str(parsed["frame_type"])
        response = ()
        is_command = bool(parsed["destination"].flag and not parsed["source"].flag)
        if is_command and parsed["poll_final"]:
            response_name = "RNR" if self._local_busy else "RR"
            response = (self._s_action(response_name, poll_final=True),)
        if name == "RR":
            self._remote_busy = False
            return DataLinkResult(True, "RR acknowledgement accepted", response)
        if name == "RNR":
            self._remote_busy = True
            return DataLinkResult(True, "RNR acknowledgement accepted", response)
        if name == "REJ":
            self._remote_busy = False
            actions = tuple(DataLinkAction("I", frame, True) for _, frame in self._outstanding)
            return DataLinkResult(
                True, "REJ accepted; inert retransmission set prepared", response + actions,
            )
        raise AssertionError("validated supervisory type became unreachable")

    def _validate_incoming(self, parsed: dict) -> str | None:
        if parsed["path"]:
            return "P2 connected links are direct only"
        destination = parsed["destination"]
        source = parsed["source"]
        if (destination.callsign, destination.ssid) != (self._local.callsign, self._local.ssid):
            return "frame is not addressed to local station"
        if (source.callsign, source.ssid) != (self._remote.callsign, self._remote.ssid):
            return "frame source is not the configured remote"
        if destination.flag == source.flag:
            return "invalid AX.25 command/response bits"
        is_command = bool(destination.flag and not source.flag)
        if parsed["frame_class"] == "I" and not is_command:
            return "I frame must be a command"
        return None

    def _ack_count(self, nr: int) -> int | None:
        sequence = self._va
        for count in range(len(self._outstanding) + 1):
            if sequence == nr:
                return count
            sequence = sequence_next(sequence)
        return None

    def _apply_ack(self, nr: int, count: int) -> None:
        if count:
            del self._outstanding[:count]
        self._va = nr

    def _s_action(self, name: str, *, poll_final: bool = False) -> DataLinkAction:
        frame = build_s_frame(
            source=self._local, destination=self._remote, frame_type=name, nr=self._vr,
            command=False, poll_final=poll_final,
        )
        return DataLinkAction(name, frame)

    def _reset_data_state(self) -> None:
        self._vs = self._vr = self._va = 0
        self._outstanding.clear()
        self._local_busy = False
        self._remote_busy = False

    def _reject(self, reason: str) -> DataLinkResult:
        self._rejected_frames += 1
        return DataLinkResult(False, reason)


def _validate_sequence(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7:
        raise ValueError("sequence number must be an integer 0..7")


__all__ = [
    "DataLinkAction", "DataLinkResult", "DataLinkSnapshot", "Modulo8DataLink",
    "build_i_frame", "build_s_frame",
]
