# 0C-P4b concrete TXBroker behind qualified access queue — staged 2026-09-02

## Status

**STAGED / HOST-ONLY — real broker class, fake modem port only.**

0C-P4b composes the host-qualified 0C-P4a `BoundedChannelAccessQueue` directly with the already-qualified P13a `TXBroker`. No adapter production code is required because the broker already satisfies P4a's narrow `FrameSubmitter.submit_frame()` protocol.

The concrete broker is enabled only inside host tests and is constructed over a plain Python fake implementing the two broker-facing methods `rf_status()` and `transmit_selector_burst()`. No `TXModemOwner`, transport, serial device, MMDVM HAT, KISS TX, daemon TX, or RF path exists in this qualification.

## Frozen base

- base checkpoint: `checkpoint/0c-p4a-bounded-access-queue-qualified`
- base SHA: `384f408af286aca34e16b0480267b890cdcbdba9`
- P4a queue capacity: 4
- P4a total request lifetime: 30 s from enqueue
- P3/P2/P1 channel-access semantics unchanged
- P13a fixed TX serializer profile unchanged: 45 opening flags, 3 closing flags, MARK start
- P5 reference selector anchor: 691 selectors / 87 packed bytes / SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

## Staged integration proof

`tests/access_queue_broker_integration_test.py` uses the real `TXBroker` and proves:

1. no broker/modem call occurs before P4a/P3 reaches READY;
2. the exact P5 FCS-valid reference frame reaches the real broker after READY;
3. the broker produces exactly 691 selectors and 87 packed bytes at the frozen SHA256;
4. broker RF-status preflight is called before the fake selector-burst operation;
5. pending selectors cause `TXBrokerBusy`, which becomes one terminal P4a downstream failure with no retry;
6. the broker's default transmit-disabled state fails closed before fake modem access;
7. a long but FCS-valid frame may enter P4a, but the broker remains authoritative for `MAX_SELECTORS` rejection and prevents fake modem access;
8. a fake-modem burst failure propagates through the broker and becomes one terminal P4a failure with no automatic retry.

## Architecture boundary

`tests/access_queue_broker_contract_test.py` proves the qualification does not import `TXModemOwner` or a serial transport. P4a remains generic and still does not import the broker. The ordinary KISS server and daemon remain unaware of P4a/P4b and have no TX broker path.

This phase validates composition only. The fake object's `transmit_selector_burst()` method stores bytes in memory; it cannot access hardware or transmit RF.

## Safety

- real `TXBroker` class instantiated: YES, host test only
- real `TXModemOwner`: NO
- modem transport: NO
- UART: NO
- KISS TX: NO
- daemon TX: NO
- product TX: NO
- RF TX: NO
- flash/GPIO/option bytes: NO

Only after this host composition is qualified can a later guarded phase consider the same access→broker path with the physically qualified modem owner, and that must occur through a one-purpose explicit physical harness before any KISS-originated or persistent product TX is connected.
