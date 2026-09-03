# 0C-P7 — Guarded KISS DATA admission host qualification

Date: 2026-09-03

## Result

**HOST QUALIFIED.** 0C-P7 is the first YWD-1278 boundary that admits a standard port-0 KISS DATA frame into the bounded transmit scheduler. The qualification is deliberately host-only: the complete software graph is exercised through a real localhost KISS TCP socket, real P6 parameter state, real P2/P1 channel-access policy, real P4e persistent half-duplex lifecycle, real P5 TXDELAY broker policy, and a real `TXModemOwner`, but the modem transport is an in-memory thread-bound fake. No POSIX serial device, UART, or RF hardware is reachable from this qualification.

Base checkpoint:

`checkpoint/0c-p6-kiss-control-plane-host-qualified` -> `860104a7dbaff3dac642b72cc040d746375e7264`

## KISS DATA boundary

For YWD-1278, a KISS DATA payload is the AX.25 frame **without** the two-byte FCS. P7 validates that body using the existing AX.25 parser and appends the FCS exactly once inside the TNC before the request reaches the qualified FCS-bearing transmit components.

Only KISS port 0 DATA is admitted. P6 control behavior remains unchanged for parameter commands and unsupported ports.

## Immutable per-request TNC context

The host vector deliberately proves that a queued DATA request cannot be mutated by later KISS parameter commands.

At admission, generation 3 contained:

- TXDELAY = 50 (500 ms, 75 opening HDLC flags)
- PERSIST = 200
- SLOTTIME = 20 (200 ms)

Immediately after admission, the live session was changed to generation 6:

- TXDELAY = 30 (300 ms)
- PERSIST = 0
- SLOTTIME = 10 (100 ms)

The admitted generation-3 request still:

1. waited for the captured 200 ms clear slot rather than the live 100 ms value;
2. accepted persistence byte 100 under captured PERSIST=200, which live PERSIST=0 would have rejected; and
3. serialized through the qualified TXDELAY=50 broker profile with 75 opening flags rather than the later TXDELAY=30 profile.

This proves that DATA admission takes one immutable, generation-tagged P6 snapshot and carries it through both channel access and serialization.

## Bounded request behavior

The new contextual P7 queue preserves the qualified P4a fail-closed behavior without modifying the historical P4a source:

- capacity defaults to 4 and includes the current head request;
- total request lifetime begins at admission and defaults to 30 seconds;
- malformed AX.25 is rejected before queue admission;
- only the current head request advances on one RSSI observation;
- each head request creates a fresh P2/P1 access attempt using its captured PERSIST/SLOTTIME values;
- READY dispatches exactly once;
- downstream failure is terminal;
- no automatic retry or same-request requeue exists.

## Full host graph proof

The localhost integration test exercised:

`TCP KISS client -> P6 control/session -> P7 DATA backend -> P7 contextual bounded queue -> P2 RSSI busy detector -> P1 p-persistent CSMA -> P4e PersistentHalfDuplexSubmitter -> contextual TXDELAY router -> real TXDelayBroker -> real TXModemOwner -> thread-bound fake MMDVM transport`

The fake wire transcript contained exactly one complete half-duplex lifecycle:

`RX_STOP -> TX_TONES -> RF-idle polling -> RX_START`

The fake modem accepted exactly one selector burst, RX was active after the post-TX restart, and every fake modem transaction plus transport close occurred on the single modem-owner thread.

The contextual router lazily created only the captured TXDELAY=50 broker profile. The later live TXDELAY=30 value was not used for the admitted frame.

## Frozen components preserved

Architecture CI locks these qualified historical sources to their existing Git blob IDs:

- P4a `src/ywd1278/tx/access_queue.py`: `d3631b549ea87cb14ce66e1020d74971c4c51392`
- P4e `src/ywd1278/tx/half_duplex.py`: `d826fd4a53d52ba359eb0b45642370db0f0cb7cc`
- P5 `src/ywd1278/tx/txdelay.py`: `b8035a58c4b48765c580dab06bcdb054a9801c8c`
- TX broker `src/ywd1278/tx/broker.py`: `1e3307dccea4f2805d32cb9be5b34f3537e29c4f`

P7 composes these boundaries rather than rewriting them.

## CI evidence

Initial P7 run #2 reached both behavioral PASS gates. Its only failure was an overbroad architecture assertion that rejected the safety phrase `no automatic retry` because it contained the words `automatic retry`; there was no implementation failure. The assertion was narrowed to inspect actual requeue/retry mechanisms.

Corrected qualification head `0443799b4822f1eabcfaf87be4a8a28cdcd92826`:

- `p7-ci` #4, run `33758497774`: **SUCCESS**
- `framework-ci` #418, run `33758497758`: **SUCCESS**
- P4d/P4e/P5/P6 historical guards: **SUCCESS**

The P7 tests are subsequently added to permanent `framework-ci` before promotion.

## Safety boundary

This host qualification does **not** authorize physical KISS-originated transmission.

- POSIX serial transport: NO
- UART opened: NO
- real modem hardware: NO
- RF transmitted: NO
- product TX enabled: NO
- flash written: NO
- GPIO/reset: NO
- option-byte writes: NO
- automatic TX retry: NO
- physical P7 harness present: NO

The contextual TXDELAY router defaults `transmit_enabled=False`. It is explicitly enabled only inside the host integration graph whose downstream modem transport is fake.

## Physical follow-on

Physical KISS-originated TX requires a separate locked stage after this host checkpoint is frozen. The planned first physical P7 packet is intentionally bounded to:

- frequency: 145.050 MHz
- RF power: 200/255
- packet count: exactly 1
- literal AX.25 path: `VIA YWDNOD`
- direct independent external decode: required
- `YWDNOD*` digipeater-repeat proof: **not required / deferred**
- automatic retry: forbidden

The previously observed `YWDNOD*` behavior remains a separate non-blocking digipeater integration item and does not invalidate P5 direct TXDELAY proof or this P7 host qualification.
