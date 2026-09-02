# 0B-P1R1 — Corrected deterministic firmware build qualification

Date: 2026-09-02

Status: **QUALIFIED**

## Scope

This qualification replaces the runtime-invalid 0B-P1 artifact with a corrected, deterministic, build-only YWD-1278 firmware artifact for the first supported MMDVM_HS Hat target.

The historical 0B-P1 checkpoint remains frozen for provenance, but its artifact SHA256 `db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3` is revoked for runtime use.

## Qualifying code boundary

The physically tested code boundary before this evidence document is:

`1cf4cf0cb3e0cbf903c9439dfb9d3a09b0b7e7b3`

Commit: `test: require repeatable read-only artifact publishing`

## Corrected clock model

The first P1 build incorrectly conflated two independent clocks. P1R1 explicitly separates them:

- STM32F103 HSE: **8,000,000 Hz**
- ADF7021 RF TCXO: **14,745,600 Hz**
- `OSC` make override: **absent**

The build wrapper verifies the exact pinned upstream MMDVM_HS_Hat recipe, which copies `configs/MMDVM_HS_Hat.h` to `Config.h` and runs normal `make` without an OSC override. The pinned upstream Makefile provides the normal F1 `CLK_DEF=8000000` HSE value while the HAT configuration independently selects `ADF7021_14_7456`.

## Exact source inputs

- Upstream repository: `juribeparada/MMDVM_HS`
- Upstream commit: `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`
- STM32F10X_Lib commit: `1debc23063f3942608e2bd62d04d5e1249c47fa3`
- Configuration: `configs/MMDVM_HS_Hat.h`
- Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`

## Physical build evidence

The build was executed on `pi5-norm` as the normal `ywd` user, without `sudo`.

Reported toolchain:

- `arm-none-eabi-gcc (15:14.2.rel1-1) 14.2.1 20241119`
- GNU Make 4.4.1

The build verified:

- `UPSTREAM_HAT_BUILD_RECIPE=PASS`
- exact pinned upstream source
- exact pinned STM32F10X_Lib submodule
- STM32 HSE = 8 MHz
- ADF7021 TCXO = 14.7456 MHz
- no OSC override
- branding transform only
- no behavioral source changes beyond generated `Config.h` and `version.h` identity transform
- firmware identity occurs exactly once
- plausible STM32 vector table
- two independent clean builds
- byte-for-byte reproducibility
- repeatable atomic artifact publication over an existing read-only artifact

## Qualified artifact

Artifact filename:

`MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Profile:

`0b-p1r1-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse`

Size:

`57316` bytes

SHA256:

`b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8`

Firmware identity:

`MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Vector evidence:

- initial SP: `0x20005000`
- reset vector: `0x080076d9`

Two independent clean builds produced the identical SHA256:

`b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8`

The final publication step reported `ATOMIC_PUBLISH=PASS` and the complete result reported `REPRODUCIBILITY=PASS`.

## Safety evidence

The P1R1 build path remained build-only:

- `HARDWARE_ACCESSED=NO`
- `RF_TRANSMITTED=NO`
- `FLASH_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

Normal product flashing remained disabled throughout this qualification. The 0B-P3 qualification write gate was also closed while P1R1 was being rebuilt and verified.

## Result

**0B-P1R1 PASS.**

This exact artifact SHA may now be promoted as the sole firmware candidate for the next guarded 0B-P3 write/readback/identity/stock-restore round-trip attempt. Promotion does not enable normal product flashing, and option-byte writes remain forbidden.
