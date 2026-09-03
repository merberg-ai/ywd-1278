# 0C-P5 — TXDELAY host policy staging

Date: 2026-09-02

Status: **staged; host-only; no RF transmitted**

Base: `checkpoint/0c-p4e-live-multicycle-qualified` at `b6b18631e9e1abaa2854f1a69a7a4dc56d08e71d`.

## Purpose

0C-P4e physically qualified persistent half-duplex RX/TX/RX operation. 0C-P5 begins the parameter layer with TXDELAY while keeping KISS-originated TX disconnected.

The historically qualified `TXBroker` remains byte-for-byte unchanged. The new `TXDelayBroker` subclasses that boundary and changes only deterministic frame preparation by resolving a construction-time TXDELAY value into a whole-number HDLC flag preamble.

## TXDELAY semantics

- parameter representation: KISS-style unsigned byte, `0..255`
- unit: 10 ms
- default: `30` = 300 ms
- Bell-202 rate: 1200 baud
- one HDLC flag: 8 selectors = 6.666666... ms
- requested delay is rounded upward to the next complete HDLC flag
- `TXDELAY=0` still emits one opening flag because a frame delimiter is mandatory
- no runtime setter exists in this phase
- the normal modem selector ceiling remains authoritative; excessive TXDELAY plus frame size fails before any modem call

The default is continuity-critical: `TXDELAY=30` resolves to exactly 45 opening flags, preserving every frozen P5/P13/P4 default serializer vector.

## Planned physical follow-on

Any RF qualification packet in this phase must attempt to use the user's `KJ6YWD-5` digipeater through its configured AX.25 alias path:

`VIA YWDNOD`

The planned fixed profiles are:

1. `TXDELAY=30` — 300 ms / 45 flags
2. `TXDELAY=50` — 500 ms / 75 flags

Both planned outgoing frames use source `KJ6YWD-10`, destination `YWD5TD`, and path `YWDNOD`. External qualification should require the direct frame and a repeated frame showing the path consumed, conventionally displayed as `YWDNOD*`.

The locked vectors are:

- 300 ms: 54 frame bytes, 817 selectors, 103 packed selector bytes, packed SHA256 `534383e423bdf4f71cdafa3da9d1bbdb0bfc165e1a14d8fbd0fd676df15be145`, 13072 generated samples
- 500 ms: 54 frame bytes, 1057 selectors, 133 packed selector bytes, packed SHA256 `f0c9b7c1e08fb9cf512fa6afa7d57b84e33f42af226e4d4957b00a6ca174cb22`, 16912 generated samples

## Safety boundary

- host-only staging
- no POSIX serial transport
- no UART
- no RF
- no GPIO/reset
- no flash
- no option-byte operations
- no KISS parameter ingress
- no KISS DATA TX
- no product TX
- no automatic retry

Physical staging must not be created until the host policy, exact default continuity, YWDNOD qualification vectors, and architecture contract are CI-green.
