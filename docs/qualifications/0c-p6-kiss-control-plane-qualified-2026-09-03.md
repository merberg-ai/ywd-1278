# 0C-P6 KISS TNC Control Plane — host qualified

Date: 2026-09-03

## Result

0C-P6 is host-qualified.  A standard KISS TCP client can now change the runtime
TNC parameter state for port 0 without gaining any transmit capability.

Qualified defaults:

- `TXDELAY=30` (300 ms request, 45 opening flags under the qualified P5 policy)
- `PERSIST=63`
- `SLOTTIME=10` (100 ms)
- `FULLDUPLEX=0`
- KISS port `0`

Supported KISS commands are TXDELAY `0x01`, PERSIST `0x02`, SLOTTIME `0x03`,
and FULLDUPLEX `0x05`.

## State and request semantics

`TNCSessionState` atomically replaces an immutable parameter snapshot for each
accepted command and advances a generation counter.  Concurrent update testing
proved 400 accepted updates produced exactly 400 generations with no lost
updates.

A future transmit admission can call `capture_tx_context()` once.  The captured
object freezes:

- the parameter generation;
- the resolved TXDELAY profile;
- PERSIST and SLOTTIME as a qualified `CSMAParameters` object.

Regression coverage proves later KISS parameter commands do not mutate that
captured context.  This is the contract P7 will use when a DATA frame is first
allowed into a bounded TX queue.

## Fail-closed controls

- any KISS port other than 0 is counted and ignored;
- supported parameter commands require exactly one payload byte;
- SLOTTIME 0 is rejected because P1 requires a non-zero clear slot;
- FULLDUPLEX nonzero is rejected on the simplex target;
- unknown commands are counted and ignored;
- malformed stream frames are discarded, counted, and the TCP stream
  resynchronizes;
- KISS DATA remains counted and rejected with no frame-submit/transmit callback.

The historical `RXOnlyBackend` tests remain green.  `TNCControlBackend` extends
that RX event source and accepts only parameter updates; RX history and live DATA
delivery to clients remain unchanged.

## Operator accounting

The control plane exposes counters for KISS messages, parameter updates and
rejections, malformed frames, unknown commands, unsupported ports, unsafe
FULLDUPLEX/SLOTTIME requests, and rejected DATA TX messages.

`TNCQueueAccounting` also normalizes the already-qualified access-queue snapshot
into queue depth/capacity, accepted requests, invalid rejections, queue-full
drops, dispatches, access timeouts, and downstream failures.  The P4a queue
implementation itself is unchanged.

## CI evidence

The initial exact staging head passed:

- `p6-ci` run `33755445058` / #2 — SUCCESS;
- `framework-ci` run `33755445048` / #410 — SUCCESS;
- historical P4d/P4e/P5 workflows — SUCCESS.

The P6 suite includes direct policy tests, real localhost KISS TCP tests,
concurrency/generation tests, malformed-stream recovery, a static architecture
contract, and the historical KISS framing/server regressions.

## Safety boundary

0C-P6 is host-only:

- KISS DATA -> TX: **DISCONNECTED**
- KISS -> concrete broker: **DISCONNECTED**
- product TX: **DISABLED**
- modem/UART/RF: **ABSENT**
- flash/GPIO/option bytes: **ABSENT**

No physical test is required for P6 because no physical path was introduced.

## Deferred digipeater observation

The two-profile P5 TXDELAY physical/direct-RF proof remains preserved at
`checkpoint/0c-p5-live-txdelay-direct-qualified-repeat-pending`
(`83c97ea91c6a914cb3614040a74606ac7a929e2e`).  Whether `KJ6YWD-5` repeats a
qualification packet as `YWDNOD*` is explicitly deferred and non-blocking.

## Next gate

0C-P7 will guard the first KISS DATA admission into the real TNC transmit
pipeline.  A DATA request must capture its P6 generation at admission, remain
bounded, pass the qualified live detector/CSMA policy, and use the qualified
persistent half-duplex lifecycle.  Any P7 physical TX qualification packet will
include `VIA YWDNOD`, but a `YWDNOD*` repeat is not required for P7 success.
