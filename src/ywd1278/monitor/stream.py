"""Read-only decoded AX.25 monitor stream.

0D-P1 deliberately composes on top of the already-qualified PacketEvent
backend instead of creating another decoder, modem owner, or packet queue.
Each monitor subscription owns exactly one existing bounded backend subscriber
queue.  History is replayed first, then live events continue in source order.

The monitor is observation-only.  It has no modem dependency, RF operation,
KISS control handler, or transmit callback.  A slow monitor therefore cannot
create a hidden unbounded backlog: the source backend's existing bounded queue
and subscriber-drop counter remain authoritative.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from queue import Empty, Queue
import time
from typing import Callable

from ywd1278.ax25 import AX25_PID_NO_L3, Address, parse_frame
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend


@dataclass(frozen=True)
class MonitorRecord:
    """One parsed monitor record returned to a reader."""

    sequence: int
    observed_at_ns: int
    history_replay: bool
    source: str
    destination: str
    path: tuple[str, ...]
    frame_class: str
    frame_type: str
    poll_final: bool
    ns: int | None
    nr: int | None
    pid: int | None
    info: bytes
    frame_no_fcs: bytes
    line: str


@dataclass(frozen=True)
class MonitorStreamSnapshot:
    """Per-reader accounting plus the upstream bounded-drop counter."""

    closed: bool
    pending_history_events: int
    queued_live_events: int
    records_returned: int
    decode_failures: int
    source_subscriber_drops: int


def _path_text(address: Address) -> str:
    text = str(address)
    return f"{text}*" if address.flag else text


def _escape_info(info: bytes) -> str:
    """Render arbitrary information bytes as one deterministic text line."""

    out: list[str] = []
    for byte in info:
        if byte == 0x5C:
            out.append("\\\\")
        elif byte == 0x0D:
            out.append("\\r")
        elif byte == 0x0A:
            out.append("\\n")
        elif byte == 0x09:
            out.append("\\t")
        elif 0x20 <= byte <= 0x7E:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def render_monitor_line(parsed: dict) -> str:
    """Return one stable, single-line TNC2-style monitor representation.

    Conventional UI/PID-F0 traffic is intentionally terse.  Connected-mode
    and control frames keep explicit frame metadata so later MCOM/MCON policy
    can filter them without reparsing display text.
    """

    source = str(parsed["source"])
    destination = str(parsed["destination"])
    path = tuple(_path_text(item) for item in parsed["path"])
    route = f"{source}>{destination}"
    if path:
        route += "," + ",".join(path)

    frame_type = str(parsed["frame_type"])
    frame_class = str(parsed["frame_class"])
    pid = parsed["pid"]
    info = bytes(parsed["info"])
    rendered = _escape_info(info)
    pf = 1 if parsed["poll_final"] else 0

    if frame_type == "UI" and pid == AX25_PID_NO_L3:
        return f"{route}:{rendered}"

    if frame_class == "I":
        descriptor = (
            f"[I ns={parsed['ns']} nr={parsed['nr']} pf={pf} "
            f"pid=0x{int(pid):02X}]"
        )
    elif frame_class == "S":
        descriptor = f"[{frame_type} nr={parsed['nr']} pf={pf}]"
    elif frame_type == "UI":
        descriptor = f"[UI pf={pf} pid=0x{int(pid):02X}]"
    else:
        descriptor = f"[{frame_type} pf={pf}]"

    return f"{route}:{descriptor}" + (f" {rendered}" if rendered else "")


def _decode_event(
    event: PacketEvent,
    *,
    sequence: int,
    observed_at_ns: int,
    history_replay: bool,
) -> MonitorRecord:
    parsed = parse_frame(event.frame_no_fcs, has_fcs=False)
    source = str(parsed["source"])
    destination = str(parsed["destination"])
    frame_type = str(parsed["frame_type"])

    # PacketEvent metadata is optional for historical/test producers.  When it
    # is present, require it to agree with the frame bytes rather than silently
    # displaying contradictory data.
    if event.source and event.source != source:
        raise ValueError(
            f"PacketEvent source mismatch: metadata={event.source!r} parsed={source!r}"
        )
    if event.destination and event.destination != destination:
        raise ValueError(
            "PacketEvent destination mismatch: "
            f"metadata={event.destination!r} parsed={destination!r}"
        )
    if event.frame_type and event.frame_type != frame_type:
        raise ValueError(
            "PacketEvent frame type mismatch: "
            f"metadata={event.frame_type!r} parsed={frame_type!r}"
        )

    return MonitorRecord(
        sequence=int(sequence),
        observed_at_ns=int(observed_at_ns),
        history_replay=bool(history_replay),
        source=source,
        destination=destination,
        path=tuple(_path_text(item) for item in parsed["path"]),
        frame_class=str(parsed["frame_class"]),
        frame_type=frame_type,
        poll_final=bool(parsed["poll_final"]),
        ns=parsed["ns"],
        nr=parsed["nr"],
        pid=parsed["pid"],
        info=bytes(parsed["info"]),
        frame_no_fcs=bytes(event.frame_no_fcs),
        line=render_monitor_line(parsed),
    )


class MonitorSubscription:
    """History-first, then live decoded view of one backend subscription."""

    def __init__(
        self,
        backend: RXOnlyBackend,
        history: list[PacketEvent],
        live_queue: Queue[PacketEvent],
        *,
        clock_ns: Callable[[], int],
    ) -> None:
        self._backend = backend
        self._pending = deque(history)
        self._live_queue = live_queue
        self._clock_ns = clock_ns
        self._closed = False
        self._sequence = 0
        self._records_returned = 0
        self._decode_failures = 0

    @property
    def snapshot(self) -> MonitorStreamSnapshot:
        return MonitorStreamSnapshot(
            closed=self._closed,
            pending_history_events=len(self._pending),
            queued_live_events=self._live_queue.qsize(),
            records_returned=self._records_returned,
            decode_failures=self._decode_failures,
            source_subscriber_drops=self._backend.snapshot.subscriber_drops,
        )

    def _convert(self, event: PacketEvent, *, history_replay: bool) -> MonitorRecord | None:
        candidate = self._sequence + 1
        try:
            record = _decode_event(
                event,
                sequence=candidate,
                observed_at_ns=self._clock_ns(),
                history_replay=history_replay,
            )
        except (TypeError, ValueError):
            self._decode_failures += 1
            return None
        self._sequence = candidate
        self._records_returned += 1
        return record

    def get(self, timeout: float | None = None) -> MonitorRecord:
        """Return the next valid record, replaying source history first.

        Invalid internal PacketEvents are counted and skipped so a monitor
        formatting fault cannot damage the running TNC.  ``queue.Empty`` is
        raised when a finite timeout expires.
        """

        if self._closed:
            raise RuntimeError("monitor subscription is closed")
        if timeout is not None and timeout < 0.0:
            raise ValueError("timeout must be >= 0")
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            if self._pending:
                event = self._pending.popleft()
                record = self._convert(event, history_replay=True)
                if record is not None:
                    return record
                continue

            if deadline is None:
                event = self._live_queue.get()
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise Empty
                event = self._live_queue.get(timeout=remaining)
            record = self._convert(event, history_replay=False)
            if record is not None:
                return record

    def read_available(self, *, maximum: int | None = None) -> list[MonitorRecord]:
        """Drain immediately available valid records without blocking."""

        if maximum is not None and maximum < 0:
            raise ValueError("maximum must be >= 0 when provided")
        out: list[MonitorRecord] = []
        while maximum is None or len(out) < maximum:
            try:
                out.append(self.get(timeout=0.0))
            except Empty:
                break
        return out

    def close(self) -> None:
        if self._closed:
            return
        self._backend.close_stream(self._live_queue)
        self._closed = True

    def __enter__(self) -> "MonitorSubscription":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class DecodedMonitorStream:
    """Factory for read-only monitor subscriptions on a PacketEvent backend."""

    def __init__(
        self,
        backend: RXOnlyBackend,
        *,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self._backend = backend
        self._clock_ns = clock_ns

    def open(self) -> MonitorSubscription:
        history, live_queue = self._backend.open_stream()
        return MonitorSubscription(
            self._backend,
            history,
            live_queue,
            clock_ns=self._clock_ns,
        )
