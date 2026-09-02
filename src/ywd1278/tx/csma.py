"""Deterministic p-persistent CSMA policy for YWD-1278.

0C-P1 is deliberately host-only.  This module decides *when* a caller may
hand an already-qualified AX.25 frame to the bounded TX broker; it has no modem,
serial, RF, KISS, GPIO, or firmware dependencies.

The policy follows classic p-persistent packet-radio channel access:

* a busy observation blocks transmission and restarts the slot timer;
* after the channel is observed clear for one complete slot, a persistence
  trial is permitted;
* an 8-bit random value passes when ``random_byte <= persist``;
* a failed persistence trial waits one more complete slot;
* any new busy observation restarts the clear-slot wait;
* an overall bounded wait timeout fails closed.

``persist`` and ``slot_time_10ms`` use the classic one-byte KISS/TNC units, but
0C-P1 does not expose KISS parameter commands or connect KISS-originated TX.
Those integrations remain later qualification gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DEFAULT_PERSIST = 63
DEFAULT_SLOT_TIME_10MS = 10
DEFAULT_MAX_WAIT_SECONDS = 30.0


class CSMAError(RuntimeError):
    """Base class for channel-access policy failures."""


class CSMATimedOut(CSMAError):
    """Raised by callers that choose exception-style handling for timeout."""


class CSMAState(str, Enum):
    WAIT_SLOT = "wait-slot"
    READY = "ready"
    TIMED_OUT = "timed-out"


@dataclass(frozen=True)
class CSMAParameters:
    """Fixed parameters for one p-persistent access attempt.

    ``persist`` is an unsigned byte.  A persistence trial succeeds when an
    unsigned random byte is <= this value, giving an exact probability of
    ``(persist + 1) / 256``.  Thus 255 always passes and 0 passes only for a
    random byte of zero.

    ``slot_time_10ms`` is also an unsigned-byte-style TNC unit but zero is
    rejected here because a zero-duration retry loop would not be a safe host
    scheduling primitive.
    """

    persist: int = DEFAULT_PERSIST
    slot_time_10ms: int = DEFAULT_SLOT_TIME_10MS
    max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS

    def __post_init__(self) -> None:
        if not 0 <= self.persist <= 255:
            raise ValueError("persist must be 0..255")
        if not 1 <= self.slot_time_10ms <= 255:
            raise ValueError("slot_time_10ms must be 1..255")
        if self.max_wait_seconds <= 0.0:
            raise ValueError("max_wait_seconds must be positive")

    @property
    def slot_seconds(self) -> float:
        return self.slot_time_10ms / 100.0

    @property
    def persistence_probability(self) -> float:
        return (self.persist + 1) / 256.0


@dataclass(frozen=True)
class CSMADecision:
    state: CSMAState
    channel_busy: bool
    persistence_trials: int
    busy_observations: int
    next_slot_at: float
    deadline_at: float
    random_byte: int | None
    reason: str

    @property
    def ready(self) -> bool:
        return self.state is CSMAState.READY

    @property
    def timed_out(self) -> bool:
        return self.state is CSMAState.TIMED_OUT


class PersistentCSMA:
    """One deterministic p-persistent channel-access attempt.

    Time is supplied explicitly by the caller.  Randomness is also supplied
    explicitly only when a clear-channel slot is due.  This makes the state
    machine deterministic in tests and prevents hidden sleeps/RNG calls from
    creeping into the safety boundary.

    A policy object is single-use.  Once READY or TIMED_OUT is reached, future
    observations return the same terminal state and can never reopen access.
    """

    def __init__(self, *, started_at: float, parameters: CSMAParameters | None = None) -> None:
        if started_at < 0.0:
            raise ValueError("started_at must be >= 0")
        self._parameters = parameters or CSMAParameters()
        self._started_at = float(started_at)
        self._deadline_at = self._started_at + self._parameters.max_wait_seconds
        self._next_slot_at = self._started_at + self._parameters.slot_seconds
        self._state = CSMAState.WAIT_SLOT
        self._persistence_trials = 0
        self._busy_observations = 0
        self._last_now = self._started_at
        self._last_decision = CSMADecision(
            state=self._state,
            channel_busy=False,
            persistence_trials=0,
            busy_observations=0,
            next_slot_at=self._next_slot_at,
            deadline_at=self._deadline_at,
            random_byte=None,
            reason="initial clear-slot wait",
        )

    @property
    def parameters(self) -> CSMAParameters:
        return self._parameters

    @property
    def decision(self) -> CSMADecision:
        return self._last_decision

    def observe(
        self,
        *,
        now: float,
        channel_busy: bool,
        random_byte: int | None = None,
    ) -> CSMADecision:
        """Advance the access attempt using one channel observation.

        ``random_byte`` must be omitted unless a clear-channel persistence slot
        is actually due.  When a trial is due it is mandatory.  This strictness
        makes accidental or premature random draws visible in tests/callers.
        """

        now = float(now)
        if now < self._last_now:
            raise ValueError("now must be monotonic for one CSMA attempt")
        self._last_now = now

        if self._state is not CSMAState.WAIT_SLOT:
            if random_byte is not None:
                raise ValueError("random_byte is not accepted after CSMA reaches a terminal state")
            return self._last_decision

        if now >= self._deadline_at:
            if random_byte is not None:
                raise ValueError("random_byte is not accepted after CSMA timeout")
            self._state = CSMAState.TIMED_OUT
            self._last_decision = self._make_decision(
                channel_busy=bool(channel_busy),
                random_byte=None,
                reason="bounded channel-access wait expired",
            )
            return self._last_decision

        if channel_busy:
            if random_byte is not None:
                raise ValueError("random_byte must not be supplied while channel is busy")
            self._busy_observations += 1
            self._next_slot_at = now + self._parameters.slot_seconds
            self._last_decision = self._make_decision(
                channel_busy=True,
                random_byte=None,
                reason="channel busy; clear-slot timer restarted",
            )
            return self._last_decision

        if now < self._next_slot_at:
            if random_byte is not None:
                raise ValueError("random_byte supplied before persistence slot is due")
            self._last_decision = self._make_decision(
                channel_busy=False,
                random_byte=None,
                reason="waiting for complete clear-channel slot",
            )
            return self._last_decision

        if random_byte is None:
            raise ValueError("random_byte is required when a clear-channel persistence slot is due")
        if not 0 <= random_byte <= 255:
            raise ValueError("random_byte must be 0..255")

        self._persistence_trials += 1
        if random_byte <= self._parameters.persist:
            self._state = CSMAState.READY
            reason = "persistence trial passed"
        else:
            self._next_slot_at = now + self._parameters.slot_seconds
            reason = "persistence trial deferred; waiting one more slot"

        self._last_decision = self._make_decision(
            channel_busy=False,
            random_byte=random_byte,
            reason=reason,
        )
        return self._last_decision

    def _make_decision(
        self,
        *,
        channel_busy: bool,
        random_byte: int | None,
        reason: str,
    ) -> CSMADecision:
        return CSMADecision(
            state=self._state,
            channel_busy=channel_busy,
            persistence_trials=self._persistence_trials,
            busy_observations=self._busy_observations,
            next_slot_at=self._next_slot_at,
            deadline_at=self._deadline_at,
            random_byte=random_byte,
            reason=reason,
        )
