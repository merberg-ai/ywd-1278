"""0G-P3 caller-driven T1/T2/T3 policy above the frozen P2 data link."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import (
    DataLinkAction,
    DataLinkResult,
    DataLinkSnapshot,
    Modulo8DataLink,
    build_s_frame,
)
from ywd1278.link.modulo8 import LinkEventResult, LinkState


@dataclass(frozen=True)
class LinkTimerConfig:
    t1_seconds: float = 3.0
    t2_seconds: float = 1.0
    t3_seconds: float = 180.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        for name, value, lower, upper in (
            ("t1_seconds", self.t1_seconds, 0.1, 60.0),
            ("t2_seconds", self.t2_seconds, 0.01, 10.0),
            ("t3_seconds", self.t3_seconds, 1.0, 3600.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or not lower <= float(value) <= upper:
                raise ValueError(f"{name} must be {lower}..{upper} seconds")
        if self.t2_seconds >= self.t1_seconds:
            raise ValueError("T2 must be shorter than T1")
        if self.t3_seconds <= self.t1_seconds:
            raise ValueError("T3 must be longer than T1")
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if not 0 <= self.max_retries <= 15:
            raise ValueError("max_retries must be 0..15")


@dataclass(frozen=True)
class LinkTimerSnapshot:
    link: DataLinkSnapshot
    t1_deadline: float | None
    t2_deadline: float | None
    t3_deadline: float | None
    t1_retries: int
    pending_delayed_ack: bool
    probe_waiting: bool
    retry_exhausted: bool
    polls: int


@dataclass(frozen=True)
class TimedLinkResult:
    accepted: bool
    reason: str
    actions: tuple[DataLinkAction, ...] = ()
    delivered: tuple[bytes, ...] = ()


class TimedModulo8DataLink:
    """Deterministic timers that never dispatch their returned frame actions."""

    def __init__(
        self,
        *,
        local: Address,
        remote: Address,
        maxframe: int = 4,
        paclen: int = 128,
        timers: LinkTimerConfig = LinkTimerConfig(),
    ) -> None:
        if not isinstance(timers, LinkTimerConfig):
            raise TypeError("timers must be LinkTimerConfig")
        self._link = Modulo8DataLink(
            local=local, remote=remote, maxframe=maxframe, paclen=paclen
        )
        self._local = Address(local.callsign, local.ssid)
        self._remote = Address(remote.callsign, remote.ssid)
        self._timers = timers
        self._last_now: float | None = None
        self._t1_deadline: float | None = None
        self._t2_deadline: float | None = None
        self._t3_deadline: float | None = None
        self._t1_retries = 0
        self._pending_t1: tuple[DataLinkAction, ...] = ()
        self._pending_ack: DataLinkAction | None = None
        self._outstanding: list[DataLinkAction] = []
        self._probe_waiting = False
        self._retry_exhausted = False
        self._polls = 0

    @property
    def snapshot(self) -> LinkTimerSnapshot:
        return LinkTimerSnapshot(
            link=self._link.snapshot,
            t1_deadline=self._t1_deadline,
            t2_deadline=self._t2_deadline,
            t3_deadline=self._t3_deadline,
            t1_retries=self._t1_retries,
            pending_delayed_ack=self._pending_ack is not None,
            probe_waiting=self._probe_waiting,
            retry_exhausted=self._retry_exhausted,
            polls=self._polls,
        )

    def connect(self, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        result = self._link.connect()
        converted = self._from_link_result(result)
        if result.accepted and converted.actions:
            self._arm_t1(converted.actions, observed)
            self._touch_idle(observed)
        return converted

    def disconnect(self, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        result = self._link.disconnect()
        converted = self._from_link_result(result)
        self._pending_ack = None
        self._t2_deadline = None
        if result.accepted and converted.actions:
            self._arm_t1(converted.actions, observed)
        elif result.after is LinkState.DISCONNECTED:
            self._clear_all_timers()
        return converted

    def send_information(self, info: bytes, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        result = self._link.send_information(info)
        if not result.accepted:
            return self._from_data_result(result)
        self._pending_ack = None  # N(R) was piggybacked on the new I frame.
        self._t2_deadline = None
        action = result.actions[0]
        self._outstanding.append(action)
        self._arm_t1(tuple(self._outstanding), observed, reset_retries=False)
        self._touch_idle(observed)
        return self._from_data_result(result)

    def set_local_busy(self, busy: bool, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        result = self._link.set_local_busy(busy)
        if result.accepted and result.actions:
            self._pending_ack = None
            self._t2_deadline = None
            self._touch_idle(observed)
        return self._from_data_result(result)

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        before = self._link.snapshot
        try:
            parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
        except (TypeError, ValueError):
            parsed = None
        result = self._link.handle_frame(frame_no_fcs)
        after = self._link.snapshot
        if not result.accepted:
            return self._from_data_result(result)

        if after.state is LinkState.DISCONNECTED:
            self._outstanding.clear()
            self._clear_all_timers()
        elif before.state is not after.state or (
            parsed is not None and parsed["frame_type"] == "SABM"
        ):
            self._outstanding.clear()
            self._pending_ack = None
            self._t2_deadline = None
            self._cancel_t1()
            self._retry_exhausted = False
            self._touch_idle(observed)
        else:
            acknowledged = before.outstanding - after.outstanding
            if acknowledged > 0:
                del self._outstanding[:acknowledged]
                if self._outstanding:
                    self._arm_t1(tuple(self._outstanding), observed)
                else:
                    self._cancel_t1()
            if self._probe_waiting and parsed is not None and (
                parsed["frame_class"] == "S" and parsed["poll_final"]
                and not parsed["destination"].flag
            ):
                self._cancel_t1()
            self._touch_idle(observed)

        actions = result.actions
        if result.delivered and len(actions) == 1:
            parsed_action = parse_frame(actions[0].frame_no_fcs, has_fcs=False)
            if parsed_action["frame_type"] == "RR" and not parsed_action["poll_final"]:
                self._pending_ack = actions[0]
                self._t2_deadline = observed + self._timers.t2_seconds
                actions = ()
        if parsed is not None and parsed["frame_type"] == "REJ":
            actions = tuple(
                replace(action, retransmission=True)
                for action in result.actions
                if action.retransmission
            )
            if self._outstanding:
                self._arm_t1(tuple(self._outstanding), observed)
        return TimedLinkResult(result.accepted, result.reason, actions, result.delivered)

    def poll(self, *, now: float) -> TimedLinkResult:
        observed = self._observe_time(now)
        self._polls += 1
        actions: list[DataLinkAction] = []
        reasons: list[str] = []
        if self._t2_deadline is not None and observed >= self._t2_deadline:
            assert self._pending_ack is not None
            actions.append(self._pending_ack)
            self._pending_ack = None
            self._t2_deadline = None
            reasons.append("T2 delayed acknowledgement due")
            self._touch_idle(observed)

        if self._t1_deadline is not None and observed >= self._t1_deadline:
            if self._t1_retries < self._timers.max_retries:
                self._t1_retries += 1
                actions.extend(replace(item, retransmission=True) for item in self._pending_t1)
                self._t1_deadline = observed + self._timers.t1_seconds
                reasons.append(f"T1 retry {self._t1_retries}/{self._timers.max_retries}")
            else:
                self._retry_exhausted = True
                self._cancel_t1()
                if self._link.snapshot.state in (
                    LinkState.CONNECTED, LinkState.AWAITING_CONNECTION
                ):
                    release = self._link.disconnect()
                    actions.extend(
                        DataLinkAction(item.frame_type, item.frame_no_fcs)
                        for item in release.actions
                    )
                reasons.append("T1 retry limit exhausted; link failed closed")

        if (
            self._t3_deadline is not None
            and observed >= self._t3_deadline
            and self._link.snapshot.state is LinkState.CONNECTED
            and self._t1_deadline is None
        ):
            probe = DataLinkAction(
                "RR",
                build_s_frame(
                    source=self._local, destination=self._remote, frame_type="RR",
                    nr=self._link.snapshot.vr, command=True, poll_final=True,
                ),
            )
            actions.append(probe)
            self._probe_waiting = True
            self._arm_t1((probe,), observed)
            self._t3_deadline = None
            reasons.append("T3 idle enquiry due")

        if not actions and not reasons:
            return TimedLinkResult(True, "no timer due")
        return TimedLinkResult(True, "; ".join(reasons), tuple(actions))

    def _arm_t1(
        self, actions: tuple[DataLinkAction, ...], now: float, *, reset_retries: bool = True,
    ) -> None:
        self._pending_t1 = actions
        self._t1_deadline = now + self._timers.t1_seconds
        if reset_retries:
            self._t1_retries = 0

    def _cancel_t1(self) -> None:
        self._t1_deadline = None
        self._pending_t1 = ()
        self._t1_retries = 0
        self._probe_waiting = False

    def _touch_idle(self, now: float) -> None:
        if self._link.snapshot.state is LinkState.CONNECTED:
            self._t3_deadline = now + self._timers.t3_seconds
        else:
            self._t3_deadline = None

    def _clear_all_timers(self) -> None:
        self._cancel_t1()
        self._pending_ack = None
        self._t2_deadline = None
        self._t3_deadline = None

    def _observe_time(self, now: float) -> float:
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise TypeError("now must be numeric")
        observed = float(now)
        if not math.isfinite(observed):
            raise ValueError("now must be finite")
        if self._last_now is not None and observed < self._last_now:
            raise ValueError("now must be monotonic")
        self._last_now = observed
        return observed

    @staticmethod
    def _from_link_result(result: LinkEventResult) -> TimedLinkResult:
        actions = tuple(DataLinkAction(item.frame_type, item.frame_no_fcs) for item in result.actions)
        return TimedLinkResult(result.accepted, result.reason, actions)

    @staticmethod
    def _from_data_result(result: DataLinkResult) -> TimedLinkResult:
        return TimedLinkResult(result.accepted, result.reason, result.actions, result.delivered)


__all__ = [
    "LinkTimerConfig", "LinkTimerSnapshot", "TimedLinkResult", "TimedModulo8DataLink",
]
