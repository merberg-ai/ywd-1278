# 0C-P4e — persistent half-duplex lifecycle host staging

Date: 2026-09-02

Status: **staged, host-only**

## Purpose

0C-P4d physically proved one guarded CSMA-controlled RX-to-TX handoff and one independently decoded RF packet. 0C-P4e turns that one-shot handoff into a reusable lifecycle boundary suitable for a persistent bidirectional packet service:

`RX active -> qualified channel access -> RX_STOP -> one downstream TX -> prove RF idle -> RX_START -> RX active`

The first P4e gate is deliberately host-only. It opens no UART and transmits no RF.

## New reusable boundary

`src/ywd1278/tx/half_duplex.py` adds `PersistentHalfDuplexSubmitter`.

The object sits behind the already-qualified P4a bounded access queue and in front of the already-qualified P4b/P4c broker/owner graph. It does not make a channel-access decision itself and contains no serializer or raw modem transaction API.

One call performs exactly one downstream submission site:

1. require clean active AX.25 RX;
2. issue `RX_STOP`;
3. require RX inactive and zero FIFO drops;
4. call the injected downstream frame submitter exactly once;
5. poll typed `RF_STATUS` and `RF_DIAG` until both pending selectors and firmware `tx_active` are zero;
6. issue `RX_START`;
7. require clean active AX.25 RX before returning the downstream receipt.

Clock and sleep functions are caller-injected for deterministic tests.

## Failure policy

- uncertain failure before the downstream submission latches the lifecycle fail-closed;
- downstream submission failure is terminal for that frame and is never retried;
- after downstream failure, RX recovery is allowed only after RF idle is proven;
- if that recovery succeeds, a later *different* request may proceed;
- once downstream TX was accepted, any idle-wait or RX-restart failure is explicitly post-transmit, latches the lifecycle, and can never cause an automatic duplicate submission;
- reconstructing the lifecycle is required after a latched failure.

## Host qualification plan

The behavioral test injects failures around RX_STOP, downstream submission, TX-idle waiting, and RX_START. It proves no-retry behavior and fail-closed latching.

The full integration test composes:

`real BoundedChannelAccessQueue -> real PersistentHalfDuplexSubmitter -> real TXBroker -> real TXModemOwner -> fake thread-bound MMDVM transport`

It requires three complete RX/TX/RX cycles, including one request that first observes BUSY. The fake transport enforces that every modem request and close happens only on the single owner thread and rejects TX while RX is active.

## Safety boundary

This stage contains no POSIX serial transport, `/dev/ttyAMA0`, real RF, KISS-originated TX, persistent product TX, flash, GPIO/reset, or option-byte access.

A later physical gate will be separately staged only after this host boundary and the complete historical CI suite are green.
