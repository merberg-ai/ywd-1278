# 0C-P8 R2 live sustained KISS TNC — staged

Date: 2026-09-03

Status: **staged / physical execution pending exact-head CI**

Base checkpoint:

`checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified`

Base SHA:

`e8d104b2c6a295219e34733d2541f89ee90318f3`

## Why R2 exists

Physical P8 attempt 1 failed before any qualification TX was accepted. The
original sustained scheduler tried to drain RX until an exact zero-length
`YWD_RX/READ`; the real AX25R4 sampler continuously produces packed raw samples
at 19.2 ksps, so RSSI/CSMA could be starved indefinitely even while RX traffic
was being captured.

Host R1 corrected that scheduler and is now frozen. R2 is a separately staged
physical attempt based on the R1 checkpoint. Attempt 1 and its branch remain
historical evidence and are not reused as an authorization boundary.

## R1 prerequisite

R2 refuses to run unless:

- `src/ywd1278/service/tnc_runtime.py` has git blob
  `f1a74ae44824bafc2b89c09e77fa416ac26bb4f1`;
- the R2 manifest names the exact R1 checkpoint and SHA;
- bounded live RX drain remains four 200-byte reads maximum per scheduling pass;
- a partial read ends the pass and an exact zero-length read is not required.

Four maximum-size reads can service 800 packed bytes, more than the AX25R4
512-byte FIFO snapshot, while still guaranteeing RSSI/CSMA an opportunity to
run against a continuously-producing sampler.

## Preserved physical implementation

R2 wraps, rather than forks, the original fixed physical harness. The preserved
attempt-1 harness blob remains:

`30a4b92162d0c4a7560424694f41cd32ad7bcd9f`

The same three fixed vectors are reused because attempt 1 accepted zero P8 TX
submissions. The KISS ingress, P2/P1 channel access, P4e half-duplex lifecycle,
P5 TXDELAY routing, modem owner and RF profile are therefore unchanged.

The original attempt-1 manifest is now marked `superseded` and `runnable=false`.
Running the old entrypoint on the R2 branch fails during manifest validation,
before UART access.

## Fixed RF profile

- device: `/dev/ttyAMA0`
- installed firmware: already-qualified AX25R4; no flash
- frequency: 145.050 MHz
- RF power: 200/255
- source: `KJ6YWD-10`
- destination: `YWD8`
- path: literal `VIA YWDNOD`
- TXDELAY sequence: 30 / 50 / 30
- PERSIST: 63
- SLOTTIME: 10
- automatic retry: forbidden
- maximum TX submissions: 3

Expected independent direct decodes remain:

`KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 1/3`

`KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 2/3`

`KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 3/3`

YWDNOD repeated/H-bit proof remains deferred and non-blocking.

## R2 diagnostics

Attempt 1 checked worker health only after dispatch, so a failed or starved
worker could be hidden behind a generic 29-second dispatch timeout. R2 adds only
operator/safety diagnostics around the preserved verifier:

- `runtime.check_health()` runs throughout every dispatch wait;
- every decoded RX frame prints `P8_R2_RX_FRAME` with source, destination,
  frame type, cycle and fresh-nonqualification state;
- approximately every two seconds while waiting, `P8_R2_WAIT` prints RX read
  transactions, packed RX bytes, decoded frames, RSSI samples, queue depth,
  BUSY state, fresh RX proof state and persistence-trial count;
- timeout errors include the complete guard snapshot, runtime counters, queue,
  ingress and control accounting.

This means an R2 failure distinguishes at least: no RX byte flow, byte flow but
no Bell-202 decode, decode without BUSY, BUSY without clear/persistence progress,
runtime worker failure, or downstream lifecycle failure.

## New arming gate

The R2 command requires:

`--confirm P8-R2-LIVE-145050-P200-SUSTAINED-3`

and the interactive phrase:

`TRANSMIT-P8-R2-SUSTAINED-KISS-THREE`

The default R2 invocation remains inert and exits before modem-owner
construction, KISS listener creation, UART access or RF transmission.

## Per-cycle proof

For each of three cycles:

1. one fixed KISS DATA body is admitted;
2. active zero-drop RX continues;
3. a fresh non-P8 FCS-valid packet must decode;
4. real RSSI BUSY must be observed;
5. after clear and one full slot, deterministic byte 255 must defer;
6. after another full slot, deterministic byte 0 may dispatch;
7. P4e performs `RX_STOP -> TX -> RF idle -> RX_START`;
8. Bell-202 streaming state resets after the half-duplex gap;
9. RX must be active again before the cycle completes.

A KISS client disconnect/reconnect remains mandatory after cycle 1. After cycle
3, a fourth non-P8 FCS-valid packet must decode and be delivered over KISS while
the TX queue is empty.

## Safety invariants

- attempt-1 accepted TX: 0
- automatic retry: no
- arbitrary frequency/power/frame/count CLI knobs: no
- raw modem TX from the R2 wrapper: no
- product TX: disabled
- daemon/systemd TX: disabled
- flash: forbidden
- GPIO/reset: forbidden
- option bytes: forbidden
- independent external direct decode: required for all three outgoing frames
- after any accepted R2 TX, a later failure must not trigger an automatic/full
  rerun; preserve the output and external-decode evidence for diagnosis.
