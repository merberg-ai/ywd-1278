# 0C-P4c — real TX owner over fake thread-bound transport

**Status:** HOST-QUALIFIED — no hardware access and no RF transmission

## Frozen base

- base checkpoint: `checkpoint/0c-p4b-real-broker-fake-modem-qualified`
- base SHA: `3b22251582f532f5b7c388bde8d5eef50b01f22d`

## Qualified software graph

P4c composes the already-qualified boundaries without adding a new production adapter:

`BoundedChannelAccessQueue -> TXBroker -> TXModemOwner -> ThreadBoundTransport(fake)`

The access queue, broker, and single-owner TX modem runtime are the real product classes. Only the modem transport is replaced with a deterministic in-memory fake that rejects any unexpected modem command and enforces owner-thread access.

## Qualified behavior

The frozen P5 reference AX.25 frame was enqueued through the real bounded access queue. Clear-channel observations were fed through the qualified P2 detector/P1 CSMA path.

Before CSMA reached READY, the fake transport observed **zero modem transactions**.

After a full clear slot and explicit persistence byte `0`, the queue dispatched exactly once through the real `TXBroker` and real `TXModemOwner`. The modem-facing sequence was exactly two transactions:

1. `YWD_RF / RF_GET_STATUS`
2. `YWD_RF / RF_TX_TONES`

The TX request retained the frozen P5 serializer anchor:

- frame bytes: `38`
- selector count: `691`
- packed selector bytes: `87`
- packed selector SHA256: `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

Both transactions occurred on the single modem-owner thread. Transport close also occurred on that same owner thread. A later RSSI observation after dispatch produced no duplicate modem transaction.

The broker used its existing `1.5 s` transaction timeout and its existing read-only RF-status preflight before the selector burst.

## CI qualification

The staged documented head was:

`d5afd9af8e4ef3d618e5c202acd076fb886f7bca`

GitHub Actions `framework-ci` run **#357** (`33706718537`) completed **SUCCESS** on that exact staged head. Both new P4c gates passed along with all earlier frozen regression/architecture/qualification gates, manifest parsing, package installation, and framework self-test.

A final exact-head CI is required after this qualification evidence is committed before `dev` promotion and checkpoint freeze.

## Safety boundary

P4c did not use the POSIX serial transport and did not open `/dev/ttyAMA0` or any other device. It did not access the HAT and does not authorize physical TX.

- POSIX serial transport used: **NO**
- UART opened: **NO**
- KISS TX connected: **NO**
- daemon/product TX connected: **NO**
- product TX enabled: **NO**
- hardware access: **NO**
- RF transmitted: **NO**
- flash written: **NO**
- GPIO accessed: **NO**
- option bytes written: **NO**

The next physical boundary must be separately guarded and explicitly qualified before this graph is connected to the real POSIX modem transport.
