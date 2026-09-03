# 0C-P4b concrete TXBroker behind qualified access queue — host qualified 2026-09-02

## Status

**HOST QUALIFIED — real broker class, fake modem port only.**

0C-P4b directly composes the host-qualified 0C-P4a `BoundedChannelAccessQueue` with the already-qualified P13a `TXBroker`. No production adapter was added because the broker already satisfies P4a's narrow `FrameSubmitter.submit_frame()` interface.

The concrete broker is exercised only over a plain Python fake implementing `rf_status()` and `transmit_selector_burst()`. No `TXModemOwner`, modem transport, serial device, MMDVM HAT, KISS TX, daemon TX, or RF path exists in this qualification.

## Frozen base

- base checkpoint: `checkpoint/0c-p4a-bounded-access-queue-qualified`
- base SHA: `384f408af286aca34e16b0480267b890cdcbdba9`
- P4a queue: capacity 4; total lifetime 30 s from enqueue; READY exactly-once; no downstream retry
- P13a broker: fixed qualified serializer; valid-FCS gate; `MAX_SELECTORS=1920`; RF pending-selector preflight; default transmit-disabled
- frozen P5 anchor: 38-byte FCS-bearing frame, 691 selectors, 87 packed bytes, SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

## Qualified integration

Framework CI #352 (`33706006503`) succeeded on head `6476faa3fc297f03883bdaf9bb72280a0cd420b3`.

The real broker composition proved:

- no broker/modem call occurs before P4a/P3 reaches READY;
- after READY, the exact P5 reference frame reaches the real `TXBroker`;
- the broker emits exactly 691 selectors / 87 packed bytes at the frozen P5 SHA256;
- broker RF-status preflight runs before the fake selector-burst call;
- pending selectors cause `TXBrokerBusy`, propagated as one terminal P4a downstream failure with no retry and no selector-burst call;
- the broker's default transmit-disabled state fails before fake modem access;
- a long FCS-valid frame may enter P4a, while the broker remains authoritative for selector-limit rejection before fake modem access;
- a synthetic fake-modem burst error propagates through `TXBrokerError` into one terminal P4a downstream failure with no automatic retry.

## Architecture boundary

P4a remains generic and does not import the broker. P4b qualification imports the concrete broker but deliberately does not import or construct `TXModemOwner` or any serial transport. The ordinary KISS server and daemon remain unaware of P4a/P4b and remain TX-disconnected.

The fake modem's `transmit_selector_burst()` only records bytes in memory. No hardware-capable modem owner or transport is reachable.

## Safety

- concrete `TXBroker`: YES, host test only
- concrete `TXModemOwner`: NO
- modem transport: NO
- UART: NO
- KISS TX: NO
- daemon TX: NO
- product TX: NO
- RF TX: NO
- flash/GPIO/option bytes: NO

The next phase is 0C-P4c: the same access queue and real broker over the real `TXModemOwner`, but still with a fake thread-bound transport. That phase will prove the full software graph and exact modem wire requests before any hardware is reopened.
