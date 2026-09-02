# 0C-P1 Deterministic p-Persistent CSMA Host Qualification — 2026-09-02

Status: **HOST-QUALIFIED — NO LIVE CHANNEL SENSOR / NO RF TX**

## Purpose

0C-P1 introduces the first channel-access policy layer above the physically qualified 0B-P13a/P13b transmit foundation. Its job is only to decide *when* a later caller may hand an already-qualified AX.25 frame to the bounded TX broker.

This phase deliberately does **not** connect a live RF busy detector, the RX runtime, TCP KISS input, the product daemon, or the modem. It performs no UART access and cannot transmit RF.

## Frozen first policy profile

- policy: p-persistent CSMA
- `PERSIST`: `63`
- exact persistence probability: `(63 + 1) / 256 = 0.25`
- `SLOTTIME`: `10` classic 10 ms units
- slot duration: `0.100 s`
- bounded maximum channel-access wait: `30.0 s`
- caller supplies monotonic time explicitly
- caller supplies channel-busy observations explicitly
- caller supplies each 8-bit persistence random value explicitly
- no hidden clock, sleep, or RNG calls exist in the policy

The existing physically qualified Bell-202 serializer remains unchanged. Its frozen 45 opening flags / 300 ms preamble are **not** redefined as configurable TXDELAY by this phase. KISS parameter transport and configurable TXDELAY remain later gates.

## Fail-closed channel semantics

The policy never assumes a channel is clear merely because no busy sample has arrived.

Initial state is `WAIT_CLEAR` with no next-slot deadline. An explicit clear observation is required before the first complete clear-channel slot begins.

The state machine then follows these rules:

1. `WAIT_CLEAR` + clear observation -> start one complete slot and enter `WAIT_SLOT`.
2. Any busy observation -> cancel any in-progress clear slot, discard its deadline, and return to `WAIT_CLEAR`.
3. `WAIT_SLOT` before the slot deadline -> remain blocked.
4. At a due clear slot -> require exactly one caller-supplied random byte.
5. Random byte `<= PERSIST` -> enter terminal `READY`.
6. Random byte `> PERSIST` -> remain blocked and start one more complete clear slot.
7. Overall deadline reached -> enter terminal `TIMED_OUT`.
8. `READY` and `TIMED_OUT` are sticky terminal states and cannot reopen.

The explicit-clear rule is important: time after a busy sample is never automatically credited as quiet time. A later clear observation starts a fresh full slot from that observation.

## Regression coverage

`tests/csma_policy_test.py` locks the behavior above, including:

- exact default parameter values
- parameter validation / invalid ranges
- no assumed initial channel state
- first explicit clear starts the first slot
- premature persistence randomness rejected
- `PERSIST=63` accepts byte `63` and rejects byte `64`
- failed persistence trial waits one additional complete slot
- busy traffic cancels an in-progress slot
- clear after busy starts a brand-new complete slot
- repeated busy observations never create a slot
- exhaustive `PERSIST=255` boundary: all 256 byte values pass
- exhaustive `PERSIST=0` boundary: exactly one byte value passes
- bounded timeout behavior
- terminal state stickiness
- monotonic caller-time enforcement

## Architecture contract

`tests/csma_policy_contract_test.py` locks the phase boundary:

- implementation is `src/ywd1278/tx/csma.py`
- no hidden `time.monotonic()` or `time.sleep()`
- no hidden random/secrets provider
- no serial device path or serial/socket import
- no `ModemOwner` / `TXModemOwner`
- no `TXBroker` dependency inside the policy
- no `YWD_RF` / `YWD_RX` command dependency
- existing broker remains modem-overlap protection only and is not silently converted into CSMA
- TCP KISS server remains TX-disconnected
- product daemon remains TX-disconnected
- physical target status remains the qualified 0B-P13b boundary

## Physical boundary retained

The latest physical target remains:

`0b-p13b-known-packet-tx-qualified`

0C-P1 changes no firmware, target RF evidence, P12a/P12b RX evidence, or P13b TX evidence.

## Qualification conclusion

**0C-P1 is host-qualified.**

YWD-1278 now has a deterministic, fail-closed p-persistent CSMA decision engine that can be tested without wall-clock timing or nondeterministic randomness. It requires explicit observed-clear time before permission can be granted and cannot transmit anything by itself.

The next gate is **0C-P2 live channel-busy / recent-RX sensing**. That phase will define the trustworthy live observation source that feeds this already-qualified policy. KISS-originated TX will remain disconnected until channel sensing and subsequent integration gates are qualified.
