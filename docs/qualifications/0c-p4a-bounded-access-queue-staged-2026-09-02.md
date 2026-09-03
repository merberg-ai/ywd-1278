# 0C-P4a bounded channel-access request queue — staged 2026-09-02

## Status

**STAGED / HOST-ONLY — no modem, broker, KISS TX, or RF path connected.**

0C-P4a adds the first request-level scheduler above the physically qualified 0C-P3 channel-access boundary. It accepts complete AX.25 frames with valid FCS into a finite queue, gives each head request a fresh P3 detector/CSMA attempt, and dispatches only after that attempt reaches READY.

The downstream endpoint is deliberately an injected `FrameSubmitter` protocol. CI uses fake submitters only. The concrete `TXBroker` is not imported or constructed by this phase.

## Frozen base

- 0C-P3 checkpoint: `checkpoint/0c-p3-live-shadow-channel-access-qualified`
- checkpoint SHA: `6303f3e49ec4ace2df3855b14f0c488aa3638926`
- P2 detector: BUSY `<=83`, CLEAR-release `>=90`, hysteresis `84..89`, recent-RX hold 250 ms
- P1 CSMA: `PERSIST=63`, `SLOTTIME=10` = 100 ms, maximum wait 30 s
- ordinary KISS TX: disconnected
- product TX: disabled

## Scheduler contract

`src/ywd1278/tx/access_queue.py` is synchronous and deterministic:

- default outstanding-request capacity: 4, including the current head;
- invalid FCS is rejected before queueing or channel-access state is created;
- default total request lifetime: 30 s measured from enqueue time;
- queue waiting consumes that same total lifetime;
- when a request reaches the head, P1 receives only the remaining lifetime budget, never more than the qualified 30 s maximum;
- only one head request is advanced by one RSSI observation;
- a terminal request is removed before the next request can begin;
- the next queued request requires a fresh later RSSI observation;
- READY invokes the injected submitter exactly once;
- downstream failure is terminal and is never automatically retried;
- caller-supplied time and persistence randomness remain explicit;
- the scheduler has no thread, hidden clock, sleep, RNG, modem, UART, serial, socket, KISS, or RF dependency.

The scheduler intentionally does not duplicate Bell-202 serialization or selector-limit validation. Those remain the responsibility of the already-qualified bounded TX broker when a later phase composes the concrete broker behind this interface.

## Staged host tests

`tests/access_queue_test.py` covers:

- no downstream call before P3/P1 READY;
- exact one-time dispatch on READY;
- later RSSI cannot duplicate the same dispatch;
- live BUSY cancels an in-progress clear slot;
- RECENT_RX stays busy-for-access;
- a new full post-busy clear slot is required;
- invalid-FCS rejection before queueing;
- strict queue capacity;
- total request lifetime measured from enqueue;
- stale request timeout without downstream call;
- downstream failure is terminal/no retry;
- two queued requests cannot consume one RSSI observation.

`tests/access_queue_contract_test.py` structurally proves the module does not import the concrete broker, TX modem owner, modem package, KISS, threading, time, random, socket, or subprocess facilities. Existing KISS and daemon modules remain unaware of P4a.

## Safety boundary

0C-P4a does not authorize RF transmission. Reaching scheduler `DISPATCHED` in CI means only that a fake injected submitter was called. No real `TXBroker`, `TXModemOwner`, UART, MMDVM HAT, KISS TX, daemon TX, flash, GPIO, option bytes, or RF transmission is reachable from this phase.

The next gate after host qualification is a separate 0C-P4b composition adapter to the already-qualified `TXBroker`, still without KISS-originated or persistent product TX and before any new physical over-air qualification.
