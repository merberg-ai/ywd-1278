# 0C-P2 live RSSI activation R2 staging

Date: 2026-09-02
Status: STAGED / CI-GREEN — PHYSICAL R2 NOT YET RUN

## Why R2 exists

Physical activation attempt 1 stopped before any candidate write because `stm32flash` informational stdout contaminated the preflight SHA256 command substitution. The programmed AX25R3 bytes themselves matched the exact qualified SHA256.

R2 preserves the original activation harness unchanged and adds `firmware/activate-rssi-live-r2.sh`, a narrow process-boundary wrapper around `stm32flash`:

- `stm32flash -r` informational stdout is redirected to stderr so readback diagnostics remain visible but cannot contaminate captured SHA256 output;
- non-read operations retain their original stdout/stderr behavior;
- no flash geometry, target, device, frequency, artifact, confirmation token, rollback logic, RF setup, modem operation, or TX policy is changed;
- the original attempt-1 harness remains preserved as historical evidence.

## Frozen physical inputs

- physical base: P13b-qualified AX25R3
- AX25R3 bytes: 59,812
- AX25R3 SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- AX25R4 candidate bytes: 59,892
- AX25R4 SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- RX frequency: 145.050 MHz
- RSSI observation: 20.0 s
- poll interval: 0.05 s
- KISS/product TX: disconnected
- carrier threshold/hysteresis: not selected
- option-byte access: forbidden

## CI

Framework CI run #302 on head `e39c9fe391d432ef6cd2d7b150ed1244b448d55f` passed the dedicated `P2 R2 clean readback stdout contract` together with all historical RX/TX/CSMA/firmware/install/self-test gates.

0C-P2 remains unqualified until the physical R2 activation and raw RSSI observation succeeds.
