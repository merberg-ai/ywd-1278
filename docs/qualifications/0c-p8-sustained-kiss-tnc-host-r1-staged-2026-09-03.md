# 0C-P8 sustained KISS TNC host R1 — staged

Date: 2026-09-03

Status: **host-only regression repair staged / physical TX unauthorized**

Base checkpoint:

`checkpoint/0c-p8-sustained-kiss-tnc-host-qualified`

Base SHA:

`a835d2500dbdb4a8eaf1ae3cae4ea662203a852a`

## Purpose

Physical P8 attempt 1 exposed a hardware-model gap in the frozen P8 scheduler.
The original host fake RX buffer was finite and eventually returned an empty
`RX_READ`; the real AX25R4 receive sampler continuously produces packed samples
at 19.2 ksps while RX is active. The original P8 scheduler could therefore
remain inside its RX backlog loop indefinitely and starve RSSI/CSMA.

R1 repairs only the P8 sustained scheduler and its host qualification coverage.
The physically-qualified P7 admission, P6 controls, P4e lifecycle, P5 TXDELAY,
TX broker, Bell-202 TX, daemon and systemd product boundaries remain frozen.

## Bounded live RX drain

R1 preserves the rule that already-captured RX backlog outranks queued TX access
without requiring the impossible condition that a live sampler momentarily
produce exactly zero bytes.

- firmware packed RX FIFO capacity: 512 bytes
- host `RX_READ` maximum: 200 bytes
- maximum reads per scheduler pass: 4
- maximum drain capacity per pass: 800 bytes
- partial read ends the current drain pass
- zero-length read is not required
- RSSI/CSMA receives a scheduling opportunity after at most four full reads

The next scheduler iteration returns to RX first, so receive backlog retains
priority while channel access can no longer be starved forever.

## New regression coverage

`tests/sustained_live_fifo_drain_regression_test.py` includes two models the
original host gate did not:

1. a continuously-producing RX source that returns a full 200-byte payload on
every read forever; `_drain_rx_fifo()` must nevertheless return after exactly
four reads;
2. a source returning one full read followed by a 37-byte partial read; the
scheduler must stop after that partial read and must not issue a third read just
to seek an exact zero.

The existing full P8 localhost KISS integration, concurrent bounded admission,
P7/P6/P4e/P5 regressions and framework suite remain mandatory.

## Safety

This stage is host-only.

- POSIX serial: no
- UART: no
- RF: no
- flash: no
- GPIO/reset: no
- option bytes: no
- automatic TX retry: no
- product/daemon TX: disabled
- physical P8 authorization: no

After exact-head CI is green, R1 will be recorded as a new host-qualified
checkpoint. Only then may a separate P8 physical R2 stage be created.
