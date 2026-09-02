# 0B-P13a Bounded TX Broker Host Qualification — 2026-09-02

Status: **HOST-QUALIFIED — NO PHYSICAL RF TX**

0B-P13a adds the first product-side transmit scheduling boundary above the already-qualified single-UART modem owner while deliberately keeping all ordinary product and TCP KISS transmit paths disconnected.

This phase does **not** change the physical qualification boundary established by 0B-P12b. The target manifest therefore remains at `0b-p12b-live-rf-kiss-qualified` until an actual guarded YWD-generated RF transmission is independently decoded and proven.

## Architecture added

### Narrow TX-capable modem owner

The physically qualified RX-only `ModemOwner` class is unchanged.

A new `TXModemOwner(ModemOwner)` subclass adds exactly one typed broker-facing method:

`transmit_selector_burst(selector_count, packed_selectors)`

That method:

- accepts only a selector count plus packed Bell-202 selector bytes;
- constructs the already-qualified `YWD_RF/TX_TONES` wire request through `protocol.rf_tx_tones_request`;
- routes the transaction through the inherited single-owner queue/thread;
- requires an ACK for `YWD_RF`;
- does not expose raw `transact`;
- does not expose RF abort or RF exit operations;
- does not add GPIO, flash, serial-open, KISS, or channel-access behavior.

The base `ModemOwner` used by P12a/P12b remains RX-only and still has no selector-burst TX method.

## Bounded TX broker

`TXBroker` is a one-worker, bounded, fail-closed queue above the TX-capable owner.

Default policy:

- `transmit_enabled=False`;
- queue capacity: `4` frames;
- submit timeout: `0.05 s`;
- transaction timeout: `1.5 s`;
- no runtime enable toggle.

A caller must explicitly construct a new broker with `transmit_enabled=True` before a frame can reach the typed owner TX operation. Merely starting the default broker cannot transmit.

## Frame admission gates

The broker accepts only complete AX.25 frames with a valid FCS.

Before queueing, it:

1. verifies AX.25 FCS;
2. serializes using the frozen 0B-P5 Bell-202 path;
3. rejects serialized bursts above the firmware limit of `1920` selectors;
4. packs selectors using the existing qualified selector representation;
5. records deterministic frame/selector hashes in a `TXReceipt`.

Invalid-FCS and oversize frames fail before any modem-facing call.

## Frozen P5 serialization profile

P13a does not introduce a new waveform or timing recipe.

The broker uses exactly:

- opening flags: `45`;
- closing flags: `3`;
- initial tone: `MARK`;
- AX.25 HDLC bit stuffing from 0B-P5;
- AX.25 NRZI from 0B-P5;
- existing packed selector format.

The exact previously physically-qualified AX25-5B reference frame remains:

`KJ6YWD-10>APYWD1:AX25-5B KISS TX TEST`

Host qualification reproduced:

- FCS-bearing frame bytes: `38`;
- selector count: `691`;
- packed selector bytes: `87`;
- packed selector SHA256: `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`;
- nominal selector duration: `691 / 1200 s`.

The fake transport saw exactly two modem-owner transactions for the reference submission: read-only `YWD_RF/GET_STATUS`, then the bit-exact `YWD_RF/TX_TONES` request. Both occurred on the inherited single modem-owner thread.

## Busy / overlap gate

Immediately before forwarding a queued selector burst, the broker performs a read-only `RF_GET_STATUS` through the owner.

If `remaining_selectors != 0`, the new burst is rejected with `TXBrokerBusy` and no TX command is submitted.

This is only a same-modem overlap guard. It is **not CSMA** and is not qualified as over-air channel-busy detection.

## Bounded queue behavior

The TX broker queue is finite.

A host qualification forced the first submission to block, filled a queue with capacity `1`, then attempted another submission. The third submission failed closed with `TXBrokerQueueFull`. Releasing the first transaction allowed the two already-admitted requests to complete normally.

No unbounded transmit backlog exists in this layer.

## KISS and product-service boundary

P13a intentionally leaves the existing KISS service untouched.

CI locks all of the following:

- KISS backend remains `RXOnlyBackend`;
- inbound KISS DATA continues to increment `tx_rejected`;
- KISS server imports no `TXBroker`;
- KISS server imports no `TXModemOwner`;
- KISS server has no `transmit_selector_burst` path;
- product daemon constructs no TX broker or TX owner;
- broker imports no KISS layer;
- broker opens no serial device or socket directly.

Therefore ordinary TCP KISS DATA still has **no path** to `YWD_RF/TX_TONES`.

## Physical safety boundary

No hardware was opened or exercised by the P13a qualification tests.

Observed/required markers:

```text
BOUNDED_TX_BROKER=PASS
DEFAULT_TX_STATE=DISABLED
VALID_FCS_REQUIRED=PASS
P5_SERIALIZER_REUSED=PASS
P5_SELECTOR_COUNT=691
P5_PACKED_SHA256=30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e
MODEM_BUSY_PREFLIGHT=PASS
QUEUE_FULL_FAIL_CLOSED=PASS
SINGLE_MODEM_OWNER_TX_PATH=PASS
KISS_TX_CONNECTED=NO
HARDWARE_UART_OPENED=NO
RF_TRANSMITTED=NO
```

Architecture contract markers:

```text
TX_BROKER_CONTRACT=PASS
P12B_PHYSICAL_EVIDENCE_FROZEN=PASS
BASE_MODEM_OWNER_RX_ONLY=PASS
TYPED_TX_OWNER_SUBCLASS=PASS
P5_FIXED_SERIALIZER_PROFILE=PASS
VALID_FCS_GATE=PASS
MAX_SELECTORS_GATE=1920
MODEM_BUSY_PREFLIGHT=PASS
DEFAULT_PRODUCT_TX=DISABLED
KISS_TX_CONNECTED=NO
DAEMON_TX_CONNECTED=NO
DIRECT_HARDWARE_PATH=ABSENT
RF_TRANSMITTED=NO
```

Full `framework-ci` run `33686344052` passed on implementation/contract head `20f3f03ba358069a17bd27df581f7d0aa7bdf523`, including every historical RX/firmware qualification contract, the bounded TX broker regression, package installation, and framework self-test.

## Qualification boundary / next step

0B-P13a proves the host architecture required to schedule a bounded YWD transmit without exposing raw modem frames or connecting external KISS input.

It does **not** prove RF transmission.

The next gate is 0B-P13b:

1. keep ordinary KISS TX disconnected;
2. use the exact packet firmware currently installed from P12a/P12b;
3. configure the physical test at `145.050 MHz`;
4. construct one known AX.25 packet locally;
5. pass it through the qualified P13a broker and typed TX owner;
6. transmit exactly that one guarded burst;
7. independently decode/verify it on a separate receiver/TNC;
8. prove RF keyup/generated-sample counters changed only as expected;
9. release the UART cleanly;
10. leave unrestricted/product/KISS TX disabled after the test.

Only after P13b physical TX proof should KISS-originated DATA be considered for connection to the broker, and even then it must pass through later channel-access/CSMA policy rather than bypassing it.
