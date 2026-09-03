# 0C-P8 sustained bounded KISS TNC — host staging

Date: 2026-09-03

Status: **staged / host fake-modem only**

Base: `checkpoint/0c-p7-live-kiss-one-shot-qualified` at `80249ab34da4c64d40d23d98d639db78d1691f5d`.

## Purpose

P7 proved one ordinary localhost KISS DATA frame end-to-end through the real qualified software graph and one guarded RF burst. P8 turns that one-shot host shape into a sustained service boundary before any persistent physical TX is authorized.

The P7/P6/P4e/P5 sources remain byte-for-byte frozen. P8 adds concurrency and service scheduling only by composition.

## Staged host architecture

- `ThreadSafeKISSDataAdmissionQueue` owns an `RLock` around the unchanged P7 `KISSDataAdmissionQueue` so threaded KISS producers and the single scheduler consumer cannot mutate the bounded deque concurrently.
- `SustainedTNCBackend` extends the P7 backend with total connection/disconnection accounting while preserving bounded KISS history/subscriber queues.
- `SustainedTNCRuntime` is one scheduler worker over an already-running, RX-active `TXModemOwner`. It does not construct a transport or configure RF.
- RX packed bytes continue through `StreamingBell202Decoder` and `PacketEvent` publication.
- RSSI is polled only while a DATA request is queued.
- Channel access remains the captured per-request P2/P1 policy from P7.
- READY still dispatches through the unchanged contextual P4e half-duplex and P5 TXDELAY graph.
- After each successful `RX_STOP -> TX -> RF idle -> RX_START`, P8 replaces the Bell-202 streaming decoder because the RX sample stream has a real discontinuity.
- Monotonic time and persistence randomness remain explicit caller-supplied dependencies.
- A downstream/lifecycle failure is terminal/fail-latched; P8 does not retry the frame.

## Host qualification scenarios

The dedicated P8 gate requires:

1. Eight concurrent DATA producers against capacity four: exactly four admissions and four queue-full drops, with no downstream call or hardware dependency.
2. One sustained real-localhost-TCP graph over a real `TXModemOwner` and fake thread-bound modem transport:
   - two KISS client sessions with disconnect/reconnect;
   - five DATA attempts total;
   - four admitted DATA requests and one intentional queue-full drop;
   - four immutable TXDELAY captures: `20`, `30`, `40`, `50`;
   - four complete P4e TX cycles;
   - five RX starts total (initial + four restarts) and four RX stops;
   - one FCS-valid Bell-202 RX frame decoded after TX and delivered from KISS history to the reconnected client;
   - four mandatory post-TX decoder resets;
   - queue depth returns to zero;
   - one modem-owner thread only;
   - zero automatic retries.
3. Operator-visible aggregate accounting for runtime, current parameters, P6 control counters, P7 DATA ingress, normalized bounded queue outcomes, TCP connections, and subscriber drops.

Dedicated P8 CI run #1 on initial candidate `84572fe0a4c2a5ed06368915a0cecec5e849644e` passed every staged step, including concurrency, sustained localhost integration, architecture contract, P7 physical-evidence preservation, P6/P4e/P5 regressions, and manifest parse. The same complete dedicated gate passed again as P8 CI run #2 on `0535027eaaa3b50f57c3948e4b383acdd7245675` before the PR was switched from draft to review for full-framework gating.

## Safety boundary

This stage is **not** a physical-TX authorization.

- POSIX serial: absent
- UART access: absent
- RF transmitted: no
- flash/GPIO/option-byte operations: absent
- generic RF configuration surface: absent
- daemon/systemd product TX: still disabled
- automatic retry: no

The separate physical follow-on remains unauthorized until the final P8 host head passes dedicated and full framework CI and a host-qualified checkpoint is frozen. Any later P8 qualification packet must use literal `VIA YWDNOD`; `YWDNOD*` repeat proof remains deferred/non-blocking.
