# 0B-P3 attempt 1 — safe failure and automatic stock recovery

Date: 2026-09-02

Status: **NOT QUALIFIED — SAFE FAILURE, STOCK RECOVERED**

## Starting state

- Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- Exact stock identity:
  `MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`
- Protected stock backup SHA256:
  `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`
- Candidate YWD artifact SHA256:
  `db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3`
- Candidate size: 57348 bytes
- Normal product `flash_enabled`: false
- P3 qualification-only write gate was enabled for this exact artifact and exact P2 stock backup.

## Physical result

The qualification harness:

1. verified the exact stock start identity;
2. entered the STM32 factory bootloader through the qualified Pi GPIO20/21 control path;
3. verified bootloader version `0x22` and device ID `0x0410`;
4. wrote the exact candidate YWD artifact;
5. read back all 57348 programmed bytes;
6. obtained the exact expected candidate SHA256:
   `db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3`;
7. restarted the application;
8. received no valid MMDVM `GET_VERSION` response after three attempts;
9. treated that as a failed qualification;
10. automatically re-entered the bootloader and restored the exact protected 131072-byte stock image;
11. restarted stock firmware and reported `EMERGENCY_STOCK_RESTORE=PASS`.

The failure therefore was **not** a transfer/programming corruption: programmed-byte readback exactly matched the candidate artifact.

## Root cause

The 0B-P1 build profile incorrectly conflated two independent clocks:

- ADF7021 RF TCXO: **14.7456 MHz** (`ADF7021_14_7456` in `configs/MMDVM_HS_Hat.h`)
- STM32F103 HSE used by the normal upstream HAT build: **8 MHz** (`CLK_DEF=8000000` in the pinned Makefile)

The revoked P1 builder explicitly passed `OSC=14745600` to `make`, overriding the STM32 HSE definition with the RF TCXO frequency.

Pinned upstream `scripts/build_fw.sh` builds the MMDVM_HS_Hat by copying `configs/MMDVM_HS_Hat.h` to `Config.h` and running `make -j4` with **no `OSC` override**. The pinned Makefile therefore uses its normal F1 default `CLK_DEF=8000000`.

This clock error is consistent with a structurally valid firmware image that programs and verifies correctly but initializes STM32 timing/UART incorrectly and does not answer `GET_VERSION`.

## Disposition

- The frozen 0B-P1 reproducibility checkpoint is retained as historical evidence only.
- Artifact SHA256 `db23bc84...420b3` is **revoked for runtime use**.
- The target's normal `flash_enabled` remains false.
- The 0B-P3 qualification-only write gate is disabled.
- 0B-P2 geometry and protected stock-backup qualification remain valid.
- A corrected `0B-P1R1` build profile must use:
  - STM32 HSE: 8,000,000 Hz via pinned upstream default;
  - ADF7021 TCXO: 14,745,600 Hz via `Config.h`;
  - no `OSC` override.
- No further firmware write is permitted until the corrected deterministic artifact is rebuilt, inspected, recorded, and explicitly promoted for a new guarded P3 attempt.

## Safety evidence

- Pi itself was not rebooted.
- No RF configuration or intended RF transmission occurred.
- Option bytes were not written.
- Exact programmed YWD bytes were read back before failure handling.
- Automatic exact-stock recovery completed successfully.
