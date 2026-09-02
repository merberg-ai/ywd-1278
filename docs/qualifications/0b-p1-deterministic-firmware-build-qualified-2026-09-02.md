# YWD-1278 0B-P1 — deterministic branded firmware build qualification

Date: 2026-09-02

This qualification records a successful build-only Raspberry Pi 5 execution of the first YWD-1278 branded STM32F103 firmware pipeline. No HAT, UART, GPIO, RF, flash, or option-byte operation was performed by the build path.

## Tested product source

YWD-1278 development head used for the successful physical build:

- commit: `a3dbd51e3038d4581eee06731cb901819758e555`
- subject: `test: require exact pinned firmware fetch`

The earlier build attempt at `2315945e8657a36c9d86dc3b1615e17fd21df3d8` failed while obtaining the pinned upstream source tree and did not begin compilation or access hardware. The successful build used the corrected explicit pinned-commit fetch path.

## Pinned firmware lineage

- upstream repository: `juribeparada/MMDVM_HS`
- upstream commit: `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`
- STM32F10X_Lib submodule: `1debc23063f3942608e2bd62d04d5e1249c47fa3`
- target configuration: `configs/MMDVM_HS_Hat.h`
- oscillator: `14745600 Hz`
- hardware target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`

The branding transform changed only generated `Config.h` plus `version.h`; the tool reported `BEHAVIORAL_CHANGES=NONE`.

## Build environment

Observed on the qualification system:

```text
Toolchain        : arm-none-eabi-gcc (15:14.2.rel1-1) 14.2.1 20241119
Make             : GNU Make 4.4.1
SOURCE_DATE_EPOCH: 1696532075
```

## Qualified artifact

```text
Artifact: MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed.bin
Size:     57348 bytes
SHA256:   db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3
Identity: MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed
```

Binary inspection passed with:

```text
VECTOR_INITIAL_SP=0x20005000
VECTOR_RESET=0x080076f9
ARTIFACT_IDENTITY_COUNT=1
```

## Reproducibility evidence

Two independent clean builds were performed from the exact pinned source and submodule.

```text
Build A SHA256: db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3
Build B SHA256: db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3
REPRODUCIBILITY=PASS
```

The two firmware binaries were byte-identical.

## Safety evidence

The build wrapper is contract-tested to contain no HAT access path. During this qualification:

```text
HARDWARE_ACCESSED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

The live HAT remained on its existing stock firmware. This qualification does not enable firmware flashing and does not populate the supported target's firmware artifact/hash write gates.

## Result

```text
YWD1278_0B_P1_DETERMINISTIC_FIRMWARE_BUILD=PASS
UPSTREAM_PIN=PASS
SUBMODULE_PIN=PASS
BRANDING_TRANSFORM=PASS
ARTIFACT_INSPECTION=PASS
REPRODUCIBILITY=PASS
FLASH_GATE_OPEN=NO
HARDWARE_ACCESSED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

0B-P1 is qualified. The next firmware-safety milestone may establish the exact supported target flash geometry and qualify a protected stock backup path while keeping firmware writes disabled until the guarded flash/restore round trip is separately approved and tested.
