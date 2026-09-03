# 0C-P4e — persistent half-duplex lifecycle host qualification

Date: 2026-09-02

Status: **host-qualified**

## Qualified boundary

0C-P4e converts the physically proven one-shot P4d-R2 half-duplex handoff into a reusable host-side lifecycle:

`qualified READY -> RX_STOP -> one downstream TX -> prove RF idle -> RX_START -> RX active`

The reusable implementation is `PersistentHalfDuplexSubmitter` in `src/ywd1278/tx/half_duplex.py`.

## Repeated real-graph proof

CI composes the real qualified software graph:

`BoundedChannelAccessQueue -> PersistentHalfDuplexSubmitter -> TXBroker -> TXModemOwner -> fake thread-bound MMDVM transport`

Three separate FCS-valid TX requests complete three full RX/TX/RX cycles. The fake wire endpoint enforces firmware-like half-duplex behavior and rejects TX while RX is active.

Observed host-cycle anchors:

- complete RX/TX/RX cycles: `3`
- RX starts: `4` (initial start plus one restart after each TX)
- RX stops: `3`
- accepted `TX_TONES` requests: `3`
- RX active after every completed cycle: yes
- all modem transactions and transport close: exactly one owner thread
- POSIX serial/UART/RF: absent

One cycle includes a BUSY RSSI observation before clear/recent-RX/slot gating, proving the repeated lifecycle remains behind the already-qualified channel-access policy.

## Failure semantics

The behavioral qualification injects failures at every important seam:

- uncertain RX_STOP/pre-transmit handoff: no downstream TX call and lifecycle latches fail-closed;
- downstream TX failure: frame is terminal and is never retried;
- downstream failure may recover RX only after RF idle is proven;
- if that recovery succeeds, a later different frame may use the lifecycle;
- TX accepted but RF never reaches idle: post-transmit failure, RX is not restarted into active TX, lifecycle latches;
- TX accepted but RX_START fails: post-transmit failure and lifecycle latches;
- after any accepted-TX lifecycle failure, the same coordinator cannot submit another frame, preventing automatic duplicates.

The implementation contains exactly one downstream `submit_frame` call site.

## Determinism and architecture

The lifecycle owns no clock, sleeping policy, randomness, modem transport, serializer, or channel-access logic. Monotonic time and sleeping are injected by its caller. The existing broker remains responsible for serialization and selector submission; P1/P2/P3/P4a remain responsible for access eligibility.

The P4e tests are included in the main `framework-ci` gate in addition to the dedicated `p4e-ci` workflow.

## Safety boundary

Host qualification performs no real UART or RF activity. KISS-originated TX and product TX remain disconnected. There is no flash, GPIO/reset, or option-byte path.

The next gate is a separately guarded physical multi-cycle RX/TX/RX qualification using fixed frames only. It must prove real RX restart and continued receive functionality after transmitted bursts before any external TX ingress is considered.
