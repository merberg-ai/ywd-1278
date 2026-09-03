# 0C-P6 KISS TNC Control Plane — staged

Date: 2026-09-03

## Purpose

0C-P6 turns classic KISS TNC parameter commands into a real, thread-safe host
control plane while deliberately leaving KISS DATA transmit ingress disconnected.
This is the last control-plane boundary before a later guarded KISS DATA ->
bounded queue -> live CSMA -> half-duplex RF qualification.

The phase starts from the frozen host-qualified TXDELAY checkpoint:

- `checkpoint/0c-p5-txdelay-host-qualified`
- `30cc677fbcc9fc9bab1aa1a18c18850ed1ef40a1`

The separate P5 `YWDNOD*` digipeater-repeat observation is explicitly deferred
and non-blocking.  Its direct TXDELAY/RF evidence remains frozen at
`checkpoint/0c-p5-live-txdelay-direct-qualified-repeat-pending`; the completed
P5 RF harness must not be rerun merely to chase the digipeater observation.

## Supported session parameters

Only KISS port 0 is accepted.  The authoritative defaults are:

| KISS parameter | Command | Default | P6 policy |
| --- | ---: | ---: | --- |
| TXDELAY | `0x01` | 30 | 0..255, 10 ms units, resolved by the qualified P5 whole-flag policy |
| PERSIST | `0x02` | 63 | 0..255, passed to the qualified P1 CSMA policy for a future request snapshot |
| SLOTTIME | `0x03` | 10 | 1..255, 10 ms units; zero is rejected because the qualified scheduler forbids a zero-duration slot |
| FULLDUPLEX | `0x05` | 0 | only zero is permitted on the simplex half-duplex target |

Unknown commands and nonzero ports are counted and ignored.  Supported parameter
commands require exactly one payload byte.  Malformed controls fail closed.
Invalid KISS byte-stream frames discarded by the incremental decoder are also
accounted without terminating the TCP service.

## Runtime snapshot semantics

`TNCSessionState` owns one immutable `TNCParameterSnapshot` under a lock.  Every
accepted parameter command atomically replaces that snapshot and increments a
generation counter.

`capture_tx_context()` captures one immutable future-TX policy bundle containing:

- parameter generation;
- resolved TXDELAY profile;
- PERSIST/SLOTTIME CSMA parameters.

A later KISS parameter update cannot alter an already captured context.  P6 does
not yet admit a KISS DATA frame into the TX queue; this capture boundary exists
so P7 can attach deterministic parameters at frame admission instead of reading
mutable session state later.

## Operator accounting

P6 exposes counters for decoded KISS messages, accepted/rejected parameter
updates, malformed frames, unknown commands, unsupported ports, rejected
FULLDUPLEX/SLOTTIME values, and rejected DATA transmit messages.

It also defines an operator-facing normalization of the already-qualified
`BoundedChannelAccessQueue.snapshot` fields, including queue depth/capacity,
accepted requests, invalid rejections, queue-full drops, dispatched requests,
access timeouts, and downstream failures.  P6 does not modify the frozen P4a
scheduler to obtain those counters.

## Safety boundary

P6 is host-only.

- KISS DATA -> TX: **DISCONNECTED**
- KISS -> concrete TX broker: **DISCONNECTED**
- product TX: **DISABLED**
- modem/UART access: **ABSENT**
- RF transmission: **NONE**
- flash/GPIO/option-byte activity: **NONE**

The historical `RXOnlyBackend` remains available unchanged in behavior.  P6
adds `TNCControlBackend` as a control-aware subclass so existing RX-only users
and tests retain their old semantics.

## Qualification gates

Before promotion, CI must prove:

1. default parameter values and qualified TXDELAY/P1-derived behavior;
2. atomic supported parameter updates and generation accounting;
3. immutable captured contexts across later updates;
4. port, malformed, unknown-command, SLOTTIME-zero and FULLDUPLEX rejection;
5. concurrent updates do not lose generations;
6. localhost KISS TCP parameter updates work while DATA remains rejected;
7. malformed KISS byte streams are counted and the server resynchronizes;
8. RX history/live delivery is unchanged;
9. no physical or concrete TX dependencies enter the P6 control module.

## Next boundary

0C-P7 will be the first guarded KISS DATA admission boundary.  A DATA frame will
need to capture the current P6 parameter generation before entering a bounded
queue, and any later RF qualification packet must include `VIA YWDNOD`.  The
separate proof that `KJ6YWD-5` actually repeats it as `YWDNOD*` remains deferred
and will not be a P7 pass requirement.
