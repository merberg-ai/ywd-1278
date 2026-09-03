# 0C-P2 live RSSI activation — preflight attempt 1

Date: 2026-09-02
Status: PRE-WRITE FALSE NEGATIVE — NO FIRMWARE WRITE OCCURRED

## Physical context

The target began on the exact P13b-qualified AX25R3 runtime identity:

`MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

The guarded 0C-P2 activation entered the qualified STM32 bootloader and read the first 59,812 programmed bytes for the frozen AX25R3 physical-base gate.

The actual readback SHA256 printed by `sha256sum` was exactly:

`a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`

which exactly matches the P13b-qualified AX25R3 artifact.

## Harness failure

`readback_prefix_sha()` invoked `stm32flash` inside command substitution without redirecting its informational stdout. As a result, `base_readback_sha` contained the complete `stm32flash` banner/read-progress text followed by the correct SHA256 instead of containing only the SHA256 string.

The wrapper therefore printed a value beginning with:

`BASE_PREFLIGHT_READBACK_SHA256=stm32flash 0.7`

and then failed the exact-string comparison with:

`[FAIL] Current programmed AX25R3 bytes do not match the exact P13b physical base`

This was a host harness false negative. The programmed bytes themselves matched the exact frozen AX25R3 SHA256.

## Safety outcome

The failure occurred before the interactive activation confirmation and before `CANDIDATE_WRITE_ATTEMPTED=1`.

Therefore:

- AX25R4 candidate write attempted: NO
- AX25R3 rollback write attempted: NO
- stock fallback write attempted: NO
- option-byte access: NO
- RF transmit: NO
- KISS/product TX: DISCONNECTED
- programmed AX25R3 bytes changed: NO

Because the wrapper had entered the STM32 bootloader for the readback, the EXIT cleanup path performed only the existing `application-restart` action and returned the unchanged AX25R3 firmware to application mode.

## Required correction

`readback_prefix_sha()` must direct `stm32flash` informational output to stderr while returning only the SHA256 on stdout. The corrected behavior must be CI-locked before another physical activation attempt.

0C-P2 remains staged and unqualified. P13b remains the latest physical qualification boundary.
