# 0C-P8 sustained bounded KISS TNC — host qualified

Date: 2026-09-03

Status: **host-qualified / fake thread-bound modem only**

Base: `checkpoint/0c-p7-live-kiss-one-shot-qualified` at `80249ab34da4c64d40d23d98d639db78d1691f5d`.

Qualified implementation head: `b7c912c4a6ddc4459f92b4c190316a308f0ed378`.

## Result

0C-P8 now has a sustained host/service boundary suitable for a later guarded physical qualification. The product daemon and systemd service still do not enable TX, and this host qualification opened no POSIX serial device and transmitted no RF.

The P7/P6/P4e/P5/TXBroker/Bell-202 TX sources remain byte-for-byte frozen. P8 adds concurrency and service scheduling only by composition.

## Qualified sustained behavior

- Real localhost threaded KISS TCP accepts ordinary port-0 DATA and classic P6 parameter updates.
- `ThreadSafeKISSDataAdmissionQueue` serializes concurrent KISS producers and the scheduler around the unchanged P7 bounded queue.
- The wrapper samples its explicitly injected monotonic clock while holding the queue lock. This preserves P7's strict monotonic-time contract even when producer and scheduler threads sampled time in the opposite order before lock acquisition.
- The sustained scheduler drains all packed bytes already waiting in the RX FIFO before advancing a queued TX request through RSSI/CSMA. Already-captured receive samples therefore cannot be overtaken by a later half-duplex TX handoff.
- Per-request P6 TXDELAY/PERSIST/SLOTTIME context remains immutable from KISS admission through P2/P1 channel access and P4e/P5 dispatch.
- Every completed P4e `RX_STOP -> TX -> RF idle -> RX_START` discontinuity resets the Bell-202 streaming decoder before new receive samples are consumed.
- Downstream/lifecycle failure remains terminal and fail-latched. There is no automatic frame retry.

## Host qualification evidence

The sustained integration proves:

- eight concurrent KISS DATA producers against queue capacity four: exactly four admitted and four queue-full drops;
- an explicit stale-pre-lock timestamp regression proving authoritative serialized queue times remain monotonic;
- two real localhost KISS client sessions with disconnect/reconnect;
- five DATA attempts, four admitted, one intentional queue-full drop;
- four immutable TXDELAY profiles: `20`, `30`, `40`, `50`;
- 30-second bounded total request lifetime, including queue wait time;
- four complete half-duplex TX cycles over the real `TXModemOwner`, P4e lifecycle and P5 router/broker with a fake thread-bound modem transport;
- five RX starts total and four RX stops;
- four mandatory post-TX Bell-202 decoder resets;
- one FCS-valid post-TX receive frame decoded after the RX FIFO was completely drained and then delivered from KISS history after client reconnect;
- queue depth returning to zero;
- zero access timeouts and zero downstream failures;
- one modem-owner thread only;
- zero subscriber drops and zero automatic retries.

The exact implementation head `b7c912c4a6ddc4459f92b4c190316a308f0ed378` passed:

- dedicated P8 push run #34, run ID `33783592110` — **success**;
- dedicated P8 PR run #35, run ID `33783599612` — **success**;
- full framework PR run #454, run ID `33783599785` — **success**;
- all 11 exact-head GitHub check runs — **success**.

## Regressions found before freeze

Two important service-level bugs were intentionally left visible until understood rather than hidden with retries or loose timing:

1. **RX FIFO backlog priority.** The first sustained worker consumed one 200-byte RX chunk and could then advance a queued TX. A Bell-202 frame can be larger than that, so a later TX could reset decoder state while the tail of an already-captured frame remained in the modem FIFO. P8 now drains the current RX FIFO to empty before TX access may advance.
2. **Concurrent timestamp ordering.** Producer and scheduler threads could sample monotonic time before taking the queue lock and then enter the frozen P7 queue in reverse timestamp order. P7 correctly rejected the backward timestamp. P8 now samples its caller-supplied clock inside the same lock that serializes queue operations, and a deterministic regression test locks that behavior.

The integration test also stopped using an artificially short eight-second request lifetime; it now uses the qualified bounded 30-second total lifetime and still requires zero timeouts.

## Safety boundary

This host qualification does **not** authorize persistent physical TX.

- POSIX serial: absent
- UART access: absent
- RF transmitted: no
- flash written: no
- GPIO/reset operations: no
- option-byte operations: no
- generic RF configuration surface: absent
- daemon/systemd product TX: disabled
- automatic retry: no

The next phase is a separate guarded physical P8 sustained-session qualification using the already-qualified AX25R4 firmware, 145.050 MHz, RF power `200/255`, fixed KISS-originated packets with literal `VIA YWDNOD`, and an independently decoded direct RF result. `YWDNOD*` repeat proof remains deferred/non-blocking.

This qualification/evidence head itself must pass exact-head CI before `checkpoint/0c-p8-sustained-kiss-tnc-host-qualified` is frozen.
