# 0C-P4d-R1 — pre-TX RSSI NAK attempt

**Status:** INCOMPLETE / SAFE PRE-TX FAILURE — no RF transmission occurred

The first physical 0C-P4d attempt reached the explicitly armed live window, but the first `YWD_RX/RSSI` request was rejected by the AX25R4 firmware with MMDVM command `0x7F` (`NAK`) before any channel-access observation or broker dispatch occurred.

## Exact observed failure

The host raised:

`ValueError: unexpected MMDVM response command 0x7F; expected 0x59`

which propagated as:

`ModemOwnerError: modem owner operation 'rx_rssi' failed`

## Root cause

The R1 harness applied the fixed P13b 145.050 MHz / power-200 profile and called `arm_rx_modem_io()`, but did not call `rx_start()` before requesting RSSI.

AX25R4 intentionally accepts RSSI telemetry only when all of the following are true:

- passive AX.25 receive capture is active;
- modem state is `STATE_AX25`;
- host TX is inactive;
- AX25 selector TX is idle.

Therefore the firmware correctly returned NAK rather than fabricating an RSSI value.

A second required correction was identified during review: the firmware intentionally rejects `YWD_RF/TX_TONES` while passive RX capture is active. A physically correct half-duplex P4d flow must therefore stop RX only after qualified channel access reaches READY and immediately before the one downstream broker submission.

## Safety result

This failure occurred before the first successful RSSI observation and before `BoundedChannelAccessQueue` could reach READY. Consequently:

- TX submissions: **0**
- RF bursts: **0**
- automatic retry: **NO**
- KISS/product TX: **DISCONNECTED**
- flash: **NO**
- GPIO/reset: **NO**
- option-byte writes: **NO**

The original staged checkpoint remains frozen. R2 must add explicit RX start/status verification, bounded FIFO draining while RSSI is sampled, and an explicit RX-stop-to-broker half-duplex handoff. Do not rerun R1.
