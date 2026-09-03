# 0C-P4c — real TX owner over fake thread-bound transport

**Status:** STAGED / HOST-ONLY — awaiting CI on the exact documented head

## Purpose

0C-P4c composes the already-qualified channel-access and transmit boundaries all the way down through the real single-owner TX modem runtime without opening a serial device or permitting RF transmission.

The software graph under test is:

`BoundedChannelAccessQueue -> TXBroker -> TXModemOwner -> ThreadBoundTransport(fake)`

No new production adapter is introduced in this phase. The existing P4a queue is used directly with the existing P13a broker, and the broker is backed by the existing `TXModemOwner`. Only the transport factory is replaced by an in-memory deterministic fake.

## Frozen base

- base checkpoint: `checkpoint/0c-p4b-real-broker-fake-modem-qualified`
- base SHA: `3b22251582f532f5b7c388bde8d5eef50b01f22d`

## Required behavior

The test enqueues the frozen P5 reference AX.25 frame and feeds clear-channel observations through the P2/P1 path. Before P1 reaches READY, the fake modem transport must observe **zero** transactions.

After a full clear slot and an explicit persistence byte `0`, the request may dispatch exactly once. The complete modem-facing wire sequence is then required to be exactly:

1. `YWD_RF / RF_GET_STATUS`
2. `YWD_RF / RF_TX_TONES`

The TX request must retain the frozen P5 serializer anchor:

- AX.25 frame bytes: `38`
- selectors: `691`
- packed selector bytes: `87`
- packed selector SHA256: `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

Both transactions and transport close must occur on the single `TXModemOwner` thread. A later RSSI observation after dispatch must not create another wire request.

## Safety boundary

P4c intentionally does **not** use the POSIX serial transport. It opens no `/dev` device and does not access the Raspberry Pi HAT. Ordinary KISS TX and daemon/product TX remain disconnected.

For this phase:

- POSIX serial transport: **NO**
- UART opened: **NO**
- KISS TX connected: **NO**
- product TX enabled: **NO**
- hardware access: **NO**
- RF transmitted: **NO**
- flash written: **NO**
- GPIO accessed: **NO**
- option bytes written: **NO**

P4c does not authorize physical TX. A later separately guarded phase is required before the real modem owner may be connected to `/dev/ttyAMA0` under channel access.
