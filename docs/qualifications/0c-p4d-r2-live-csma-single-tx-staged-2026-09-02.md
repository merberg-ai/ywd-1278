# 0C-P4d-R2 — guarded live CSMA single TX with explicit RX-to-TX handoff

**Status:** STAGED / NOT PHYSICALLY RUN

R2 supersedes the physically incomplete P4d-R1 harness after R1 correctly received an AX25R4 NAK on its first RSSI poll. R1 had armed modem IO but had not started passive AX.25 receive capture.

R2 preserves the same one fixed qualification frame, 145.050 MHz frequency, RF power 200/255, detector thresholds, P1 CSMA parameters, one-submission limit, no-retry policy, and independent external decode requirement.

The corrected physical sequence is:

`SET_FREQ -> SET_CONFIG -> RX_START -> verify active RX -> poll RSSI + drain RX FIFO -> require real BUSY -> RECENT_RX -> CLEAR -> full P1 slot -> 255 defer -> full P1 slot -> 0 READY -> RX_STOP -> verify RX inactive -> TXBroker.submit_frame() -> exactly one RF burst`

The RX stop is not optional: qualified AX25R4 firmware intentionally rejects `YWD_RF/TX_TONES` while passive RX capture is active. The handoff therefore models the real half-duplex transition required by the product rather than bypassing a firmware guard.

During the receive/channel-access portion R2 drains up to 200 packed bytes on each 50 ms cycle and periodically checks RX3 status. Any FIFO drop, loss of active RX state before READY, unexpected TX diagnostic activity, second downstream dispatch, or setup mismatch fails closed.

Safety remains rigid:

- one fixed packet only: `KJ6YWD-10>YWD4D:YWD-1278 P4D CSMA VERIFY 1/1`
- maximum TX submissions: 1
- automatic retry: NO
- live BUSY required before any TX eligibility
- KISS/product TX: disconnected
- flash/GPIO/reset/option bytes: forbidden
- default invocation: dry-run; exits before TXModemOwner construction
- physical mode requires exact CLI token plus exact interactive phrase
- external over-air decode required before qualification promotion
