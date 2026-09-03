# 0C-P8 sustained bounded KISS TNC — host qualified

Date: 2026-09-03

Status: **host-qualified / physical sustained qualification pending**

Base checkpoint: `checkpoint/0c-p7-live-kiss-one-shot-qualified` -> `80249ab34da4c64d40d23d98d639db78d1691f5d`.

## Qualified boundary

P8 adds the persistent service/concurrency layer around the unchanged P7 path. It does not modify the P7 admission queue, P6 control state, P4e half-duplex coordinator, P5 TXDELAY serializer/broker, or Bell-202 TX implementation.

The qualified host graph is:

`threaded localhost KISS clients -> SustainedTNCBackend -> ThreadSafeKISSDataAdmissionQueue -> frozen P7 contextual queue/P2/P1 -> frozen P4e -> frozen P5 -> real TXModemOwner -> fake thread-bound modem`

The sustained runtime simultaneously drains the RX3 FIFO through `StreamingBell202Decoder`, publishes decoded frames to KISS history/subscribers, checks RX FIFO health, and polls RSSI only while TX DATA is queued. After every successful P4e `RX_STOP -> TX -> RF idle -> RX_START` cycle, it replaces the streaming Bell-202 decoder because the RF half-duplex gap breaks sample continuity.

Monotonic time and persistence randomness remain explicit caller dependencies. No hidden RNG was introduced.

## Qualification results

### Concurrent admission

Eight simultaneous valid KISS DATA producers targeted a capacity-four queue. Exactly four requests were admitted and exactly four were rejected as queue-full. The frozen P7 queue remained intact and was protected only by the P8 composition lock. No downstream submitter or hardware path was invoked.

### Sustained localhost integration

The full host integration used real TCP KISS, real P6/P7/P2/P1/P4e/P5 classes, a real `TXModemOwner`, and a stateful fake transport that enforces owner-thread access.

Results:

- KISS client sessions: 2
- disconnect/reconnect: proved
- DATA attempts: 5
- DATA admitted: 4
- intentional queue-full drops: 1
- immutable TXDELAY profiles, in queue order: `20`, `30`, `40`, `50`
- completed sustained TX cycles: 4
- RX starts: 5 (initial + four post-TX restarts)
- RX stops: 4
- post-TX Bell-202 decoder resets: 4
- queue depth at completion: 0
- automatic TX retries: 0
- fake modem owner threads: exactly 1
- subscriber drops: 0

After the first TX cycle, the fake modem was injected with a complete FCS-valid Bell-202 capture while no KISS client was connected. The sustained runtime decoded it after the mandatory post-TX decoder reset and stored it in KISS history. The second TCP client then reconnected and received that exact RX frame from history before admitting the fourth TX request. This proves the host service continues useful receive operation across TX and client reconnect boundaries.

### Operator accounting

A single snapshot aggregates:

- sustained runtime state/counters;
- current P6 parameter snapshot;
- P6 control counters;
- P7 DATA ingress counters;
- normalized bounded queue accepted/full-drop/access-timeout/downstream-failure counters;
- total/current TCP client connection counters;
- KISS subscriber drops.

## CI evidence

- dedicated P8 run #1: success on initial implementation candidate `84572fe0a4c2a5ed06368915a0cecec5e849644e`;
- dedicated P8 run #2: success on staged documentation head `0535027eaaa3b50f57c3948e4b383acdd7245675`;
- full historical framework PR run #439: success before host-state promotion;
- P8 tests are now included in permanent `framework-ci` and `p8-ci` also runs on `dev`.

The final feature head still requires one exact-head dedicated P8 + framework pass before `dev` may be fast-forwarded and the host-qualified checkpoint frozen.

## Safety boundary

P8 host qualification does **not** authorize physical sustained TX and does not enable the product daemon.

- POSIX serial transport: absent
- UART opened: no
- RF transmitted: no
- generic frequency/power configuration added: no
- daemon/systemd product TX enabled: no
- flash written: no
- GPIO/reset accessed: no
- option bytes written: no
- automatic retry: no

The separately guarded physical P8 follow-on remains pending. Its test packets must use literal `VIA YWDNOD`; observation of a `YWDNOD*` repeat remains deferred/non-blocking.
