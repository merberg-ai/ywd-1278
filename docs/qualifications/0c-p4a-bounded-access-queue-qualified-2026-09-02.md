# 0C-P4a bounded channel-access request queue — host qualified 2026-09-02

## Status

**HOST QUALIFIED — fake downstream only; no real TX broker or RF path connected.**

0C-P4a is the first request-level scheduler above the physically qualified 0C-P3 channel-access boundary. It accepts complete FCS-valid AX.25 frames into a finite queue, gives the head request a fresh P3 detector/CSMA attempt, and permits a downstream call only after the qualified access policy reaches READY.

## Frozen base

- base checkpoint: `checkpoint/0c-p3-live-shadow-channel-access-qualified`
- base SHA: `6303f3e49ec4ace2df3855b14f0c488aa3638926`
- P2 detector: BUSY `<=83`, CLEAR-release `>=90`, hysteresis `84..89`, recent-RX hold 250 ms
- P1 CSMA: `PERSIST=63`, `SLOTTIME=10` = 100 ms, maximum wait 30 s
- ordinary KISS TX: disconnected
- product TX: disabled

## Qualified scheduler semantics

`BoundedChannelAccessQueue` is synchronous and deterministic. Its default outstanding-request capacity is 4, including the current head. Complete AX.25 FCS is verified before queue admission. Every accepted request receives a fixed 30-second total lifetime beginning at enqueue time, so queue waiting consumes the same deadline and cannot create arbitrarily stale later transmissions.

Only the head request can consume an RSSI observation. A request reaching the head receives a fresh `ShadowChannelAccessAttempt` with no more than the remaining total lifetime. BUSY and RECENT_RX retain the already-qualified P3 fail-closed semantics, including cancellation of in-progress clear slots. Randomness remains caller supplied and is used only when P1 says a clear persistence slot is actually due.

READY is consumed exactly once: the scheduler invokes the injected `FrameSubmitter.submit_frame()` once, removes that request, and never automatically retries it. A downstream exception is terminal. The next queued request cannot consume the RSSI observation that completed the prior request; it begins only after a fresh later observation.

The scheduler intentionally does not duplicate the P13a broker's Bell-202 serializer, selector-count gate, modem pending-selector preflight, or modem transaction logic. Those remain at the already-qualified broker boundary for later composition.

## CI qualification

Framework CI #346 (`33705580315`) succeeded on initial P4a head `f9f87c28df3b21ac2d8402d6f20646554036f835`.

The P4a regression proved:

- FCS-invalid frames are rejected before queueing;
- queue capacity is strict;
- total request lifetime begins at enqueue;
- BUSY cancels access and RECENT_RX remains busy-for-access;
- READY dispatches exactly once;
- later RSSI cannot duplicate a completed dispatch;
- stale requests time out without downstream submission;
- downstream failure is terminal and not retried;
- two queued requests cannot dispatch from one RSSI observation;
- all downstream calls in CI go only to fake recorder/failure objects.

The architecture contract structurally proves `access_queue.py` imports no concrete `TXBroker`, modem package, TX owner, KISS package, threading, clock/sleep, RNG, socket, or subprocess facility.

## Safety boundary

No physical qualification is required for P4a because it contains no hardware-capable object. `DISPATCHED` in this phase means only that an injected fake `FrameSubmitter` was called after READY.

- concrete `TXBroker`: not connected
- `TXModemOwner`: not connected
- KISS TX: disconnected
- product TX: disabled
- UART/modem access: none
- RF transmitted: no
- flash/GPIO/option bytes: none

The next phase, 0C-P4b, may compose this qualified queue with the already-qualified concrete `TXBroker` using fake modem ownership first. That composition must remain host-only and keep KISS/product TX disconnected before any new guarded over-air qualification is considered.
