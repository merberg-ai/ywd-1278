"""0H-P11 bounded caller-driven forwarding coordinator; no runtime scheduler or RF.

This layer composes frozen P8 preparations with an injected delivery driver. It
never opens a link, mutates mailbox storage, schedules itself, retries an
uncertain message, or transmits RF. Accepted remote delivery produces only an
inert commit intent for a future physically-qualified storage transition.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from ywd1278.ax25 import Address
from ywd1278.node.forwarding import ForwardDisposition, ForwardEnvelope
from ywd1278.node.forwarding_integration import (
    MAX_FORWARD_BATCH,
    ForwardBatchResult,
    MailboxForwardingPlanner,
    PreparedForwardMessage,
)


class ForwardDeliveryDisposition(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class ForwardDeliveryReceipt:
    disposition: ForwardDeliveryDisposition
    reason: str


@dataclass(frozen=True)
class ForwardCommitIntent:
    message_id: int
    destination: Address
    next_hop: Address
    trace: tuple[Address, ...]


@dataclass(frozen=True)
class ForwardAttempt:
    message_id: int
    destination: Address
    next_hop: Address
    receipt: ForwardDeliveryReceipt


@dataclass(frozen=True)
class ForwardCoordinatorResult:
    accepted: bool
    reason: str
    attempts: tuple[ForwardAttempt, ...] = ()
    commit_intents: tuple[ForwardCommitIntent, ...] = ()
    skipped_message_ids: tuple[int, ...] = ()


class ForwardPlanner(Protocol):
    def prepare_batch(self, envelopes: tuple[ForwardEnvelope, ...]) -> ForwardBatchResult: ...


ForwardDeliveryDriver = Callable[[PreparedForwardMessage], ForwardDeliveryReceipt]


class HostForwardingCoordinator:
    """Execute one bounded caller-requested batch against an injected driver."""

    def __init__(
        self,
        *,
        planner: ForwardPlanner,
        delivery_driver: ForwardDeliveryDriver,
        enabled: bool,
        max_batch: int = MAX_FORWARD_BATCH,
    ) -> None:
        if not hasattr(planner, "prepare_batch"):
            raise TypeError("planner must provide prepare_batch")
        if not callable(delivery_driver):
            raise TypeError("delivery_driver must be callable")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= MAX_FORWARD_BATCH:
            raise ValueError(f"max_batch must be an integer 1..{MAX_FORWARD_BATCH}")
        self._planner = planner
        self._delivery_driver = delivery_driver
        self._enabled = enabled
        self._max_batch = max_batch

    def run_once(self, envelopes: tuple[ForwardEnvelope, ...]) -> ForwardCoordinatorResult:
        if not isinstance(envelopes, tuple):
            raise TypeError("envelopes must be a tuple")
        if not self._enabled:
            return ForwardCoordinatorResult(True, "forwarding disabled; no work performed")
        if not 1 <= len(envelopes) <= self._max_batch:
            return ForwardCoordinatorResult(
                False, f"forward batch must contain 1..{self._max_batch} envelopes"
            )

        prepared = self._planner.prepare_batch(envelopes)
        if not prepared.accepted:
            return ForwardCoordinatorResult(False, prepared.reason)

        attempts: list[ForwardAttempt] = []
        commits: list[ForwardCommitIntent] = []
        skipped: list[int] = []

        for item in prepared.preparations:
            if item.decision.disposition is not ForwardDisposition.FORWARD or item.message is None:
                skipped.append(item.envelope.message_id)
                continue

            message = item.message
            try:
                receipt = self._delivery_driver(message)
            except Exception as exc:  # delivery may have become externally visible
                receipt = ForwardDeliveryReceipt(
                    ForwardDeliveryDisposition.UNCERTAIN,
                    f"delivery driver raised {type(exc).__name__}: {exc}",
                )
            if not isinstance(receipt, ForwardDeliveryReceipt):
                receipt = ForwardDeliveryReceipt(
                    ForwardDeliveryDisposition.UNCERTAIN,
                    "delivery driver returned an invalid receipt",
                )

            attempt = ForwardAttempt(
                message.message_id,
                message.destination,
                message.next_hop,
                receipt,
            )
            attempts.append(attempt)

            if receipt.disposition is ForwardDeliveryDisposition.ACCEPTED:
                commits.append(
                    ForwardCommitIntent(
                        message.message_id,
                        message.destination,
                        message.next_hop,
                        message.trace,
                    )
                )
                continue

            # Fail closed on any rejected/uncertain delivery. There is no
            # automatic retry and later batch entries are not attempted.
            return ForwardCoordinatorResult(
                False,
                f"delivery stopped after {receipt.disposition.value.lower()} result",
                tuple(attempts),
                tuple(commits),
                tuple(skipped),
            )

        return ForwardCoordinatorResult(
            True,
            "bounded forwarding batch completed",
            tuple(attempts),
            tuple(commits),
            tuple(skipped),
        )


__all__ = [
    "ForwardDeliveryDisposition",
    "ForwardDeliveryReceipt",
    "ForwardCommitIntent",
    "ForwardAttempt",
    "ForwardCoordinatorResult",
    "ForwardPlanner",
    "ForwardDeliveryDriver",
    "HostForwardingCoordinator",
]
