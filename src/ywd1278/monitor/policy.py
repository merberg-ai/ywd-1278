"""Classic-TNC-style monitor visibility controls over frozen 0D-P1 records.

0D-P2 intentionally implements policy, not a command shell.  Future 0E console
code may bind textual commands to this typed state, but this module has no
terminal, socket, KISS-control, modem, or transmit dependency.

Semantics follow the familiar TNC shape:

* MCOM OFF hides AX.25 protocol/control frames (S frames and non-UI U frames).
  Information frames (I) and unconnected information frames (UI) remain
  monitor-eligible.
* MCON OFF, while a local connected-mode session exists, hides eligible
  third-party traffic but still permits frames addressed to the local station.
  Since native connected mode is a later phase, that session/address context is
  supplied explicitly by the future link layer rather than guessed here.
* MRPT ON includes the complete decoded digipeater path, including P1's `*`
  repeated marker.  MRPT OFF changes presentation only; MonitorRecord.path is
  never altered.

Defaults are MCOM OFF, MCON OFF, MRPT ON.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from .stream import MonitorRecord


@dataclass(frozen=True)
class MonitorPolicySnapshot:
    generation: int
    mcom: bool
    mcon: bool
    mrpt: bool


@dataclass(frozen=True)
class MonitorViewContext:
    """Connection context supplied by a future local AX.25 link layer."""

    local_connected: bool = False
    addressed_to_local: bool = False

    def __post_init__(self) -> None:
        if type(self.local_connected) is not bool:
            raise TypeError("local_connected must be bool")
        if type(self.addressed_to_local) is not bool:
            raise TypeError("addressed_to_local must be bool")
        if self.addressed_to_local and not self.local_connected:
            raise ValueError("addressed_to_local requires local_connected")


@dataclass(frozen=True)
class MonitorViewDecision:
    visible: bool
    line: str | None
    suppression_reason: str | None
    policy_generation: int


def _require_bool(name: str, value: bool) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool")
    return value


def _requires_mcom(record: MonitorRecord) -> bool:
    """Return True for AX.25 protocol/control traffic gated by MCOM."""

    if record.frame_class == "S":
        return True
    if record.frame_class == "U" and record.frame_type != "UI":
        return True
    return False


def _line_for_mrpt(record: MonitorRecord, *, mrpt: bool) -> str:
    if mrpt or not record.path:
        return record.line
    _header, separator, tail = record.line.partition(":")
    if not separator:
        raise ValueError("0D-P1 monitor line has no header separator")
    return f"{record.source}>{record.destination}:{tail}"


class MonitorPolicyState:
    """Thread-safe, generation-tagged monitor policy state."""

    def __init__(self, *, mcom: bool = False, mcon: bool = False, mrpt: bool = True) -> None:
        self._lock = RLock()
        self._generation = 0
        self._mcom = _require_bool("mcom", mcom)
        self._mcon = _require_bool("mcon", mcon)
        self._mrpt = _require_bool("mrpt", mrpt)

    @property
    def snapshot(self) -> MonitorPolicySnapshot:
        with self._lock:
            return MonitorPolicySnapshot(
                generation=self._generation,
                mcom=self._mcom,
                mcon=self._mcon,
                mrpt=self._mrpt,
            )

    def update(
        self,
        *,
        mcom: bool | None = None,
        mcon: bool | None = None,
        mrpt: bool | None = None,
    ) -> MonitorPolicySnapshot:
        """Atomically replace any supplied controls.

        The generation increments exactly once when the effective policy
        changes and does not increment for an idempotent update.
        """

        if mcom is not None:
            mcom = _require_bool("mcom", mcom)
        if mcon is not None:
            mcon = _require_bool("mcon", mcon)
        if mrpt is not None:
            mrpt = _require_bool("mrpt", mrpt)

        with self._lock:
            next_mcom = self._mcom if mcom is None else mcom
            next_mcon = self._mcon if mcon is None else mcon
            next_mrpt = self._mrpt if mrpt is None else mrpt
            if (next_mcom, next_mcon, next_mrpt) != (
                self._mcom,
                self._mcon,
                self._mrpt,
            ):
                self._mcom = next_mcom
                self._mcon = next_mcon
                self._mrpt = next_mrpt
                self._generation += 1
            return MonitorPolicySnapshot(
                generation=self._generation,
                mcom=self._mcom,
                mcon=self._mcon,
                mrpt=self._mrpt,
            )

    def set_mcom(self, value: bool) -> MonitorPolicySnapshot:
        return self.update(mcom=value)

    def set_mcon(self, value: bool) -> MonitorPolicySnapshot:
        return self.update(mcon=value)

    def set_mrpt(self, value: bool) -> MonitorPolicySnapshot:
        return self.update(mrpt=value)

    def apply(
        self,
        record: MonitorRecord,
        *,
        context: MonitorViewContext | None = None,
    ) -> MonitorViewDecision:
        """Apply one immutable policy snapshot to one immutable P1 record."""

        if not isinstance(record, MonitorRecord):
            raise TypeError("record must be MonitorRecord")
        if context is None:
            context = MonitorViewContext()
        if not isinstance(context, MonitorViewContext):
            raise TypeError("context must be MonitorViewContext")

        policy = self.snapshot

        if context.local_connected and not policy.mcon and not context.addressed_to_local:
            return MonitorViewDecision(
                visible=False,
                line=None,
                suppression_reason="MCON",
                policy_generation=policy.generation,
            )

        if not policy.mcom and _requires_mcom(record):
            return MonitorViewDecision(
                visible=False,
                line=None,
                suppression_reason="MCOM",
                policy_generation=policy.generation,
            )

        return MonitorViewDecision(
            visible=True,
            line=_line_for_mrpt(record, mrpt=policy.mrpt),
            suppression_reason=None,
            policy_generation=policy.generation,
        )
