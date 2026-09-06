"""0H-P8 bounded mailbox-to-forwarding work preparation; no dispatcher."""
from __future__ import annotations
from dataclasses import dataclass

from ywd1278.ax25 import Address
from ywd1278.node.forwarding import (
    ForwardDecision, ForwardDisposition, ForwardEnvelope, StaticForwardingPolicy,
)
from ywd1278.node.mailbox import MailboxError, MailboxStore

MAX_FORWARD_BATCH = 8
FORWARD_BODY_CHUNK_BYTES = 128

@dataclass(frozen=True)
class PreparedForwardMessage:
    message_id: int
    sender: Address
    destination: Address
    next_hop: Address
    subject: str
    body_chunks: tuple[bytes, ...]
    trace: tuple[Address, ...]

@dataclass(frozen=True)
class ForwardPreparation:
    envelope: ForwardEnvelope
    decision: ForwardDecision
    message: PreparedForwardMessage | None = None

@dataclass(frozen=True)
class ForwardBatchResult:
    accepted: bool
    reason: str
    preparations: tuple[ForwardPreparation, ...] = ()

class MailboxForwardingPlanner:
    """Read qualified storage and return immutable forwarding work descriptions."""
    def __init__(self, *, store: MailboxStore, policy: StaticForwardingPolicy) -> None:
        if not isinstance(store, MailboxStore): raise TypeError("store must be MailboxStore")
        if not isinstance(policy, StaticForwardingPolicy): raise TypeError("policy must be StaticForwardingPolicy")
        self._store=store; self._policy=policy

    def prepare(self, envelope: ForwardEnvelope) -> ForwardPreparation:
        decision=self._policy.decide(envelope)
        if decision.disposition is not ForwardDisposition.FORWARD:
            return ForwardPreparation(envelope,decision)
        destination=Address(envelope.destination.callsign,envelope.destination.ssid)
        try: stored=self._store.read_for(destination,envelope.message_id)
        except MailboxError as exc:
            return ForwardPreparation(envelope,ForwardDecision(ForwardDisposition.HOLD,f"mailbox unavailable: {exc}",next_trace=decision.next_trace))
        if stored is None:
            return ForwardPreparation(envelope,ForwardDecision(ForwardDisposition.HOLD,"message not found for forwarding destination",next_trace=decision.next_trace))
        assert decision.next_hop is not None
        sender=Address.parse(stored.sender)
        chunks=tuple(stored.body[i:i+FORWARD_BODY_CHUNK_BYTES] for i in range(0,len(stored.body),FORWARD_BODY_CHUNK_BYTES))
        message=PreparedForwardMessage(stored.message_id,sender,destination,
            Address(decision.next_hop.callsign,decision.next_hop.ssid),stored.subject,chunks,
            tuple(Address(x.callsign,x.ssid) for x in decision.next_trace))
        return ForwardPreparation(envelope,decision,message)

    def prepare_batch(self, envelopes: tuple[ForwardEnvelope, ...]) -> ForwardBatchResult:
        if not isinstance(envelopes,tuple): raise TypeError("envelopes must be a tuple")
        if not 1<=len(envelopes)<=MAX_FORWARD_BATCH:
            return ForwardBatchResult(False,f"forward batch must contain 1..{MAX_FORWARD_BATCH} envelopes")
        keys=[]
        for envelope in envelopes:
            if not isinstance(envelope,ForwardEnvelope): raise TypeError("batch entries must be ForwardEnvelope")
            key=(envelope.message_id,str(envelope.destination))
            if key in keys: return ForwardBatchResult(False,"duplicate message in forward batch")
            keys.append(key)
        return ForwardBatchResult(True,"bounded forward batch prepared",tuple(self.prepare(x) for x in envelopes))

__all__=["MAX_FORWARD_BATCH","FORWARD_BODY_CHUNK_BYTES","PreparedForwardMessage","ForwardPreparation","ForwardBatchResult","MailboxForwardingPlanner"]
