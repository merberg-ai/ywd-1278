# YWD-1278 firmware build — 0B-P1

0B-P1 establishes a deterministic, inspectable YWD-1278 firmware build for the first supported STM32F103/ADF7021 simplex HAT. It is deliberately **build-only**. Nothing in this phase is allowed to access the HAT, key RF, enter the STM32 bootloader, write flash, or touch option bytes.

## Exact source lineage

The build contract is pinned in `firmware/tooling/build-manifest.json`:

- upstream repository: `juribeparada/MMDVM_HS`;
- upstream commit: `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`;
- STM32F10X_Lib submodule: `1debc23063f3942608e2bd62d04d5e1249c47fa3`;
- target configuration: exact `configs/MMDVM_HS_Hat.h` from that commit;
- target configuration blob: `1c526b41dd96ea68823f2e83442a8a76fd59590a`;
- upstream `version.h` blob: `4239a854ec09ee90847468f931e1455ee461e2de`;
- Make target: `hs`;
- oscillator: `14745600` Hz.

The pinned HAT configuration selects `MMDVM_HS_HAT_REV12`, ADF7021, 14.7456 MHz TCXO, simplex operation, and `STM32_USART1_HOST`. It is the same upstream configuration template used by the qualified YWD-MMDVM engineering work.

## Branding transform

`firmware/tooling/apply_branding.py` accepts only the exact pinned source state. The build wrapper first replaces root `Config.h` with a byte-identical copy of the pinned HAT template. The branding transformer then changes only the firmware `DESCRIPTION` in `version.h`.

0B-P1 expected identity:

```text
MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed
```

The wording intentionally retains CA6JAU/upstream attribution. No modem/RF behavior is changed in this baseline firmware build.

## Build command

Run as the normal user, not root:

```bash
./firmware/build-ywd1278.sh
```

The default mode performs two independent clean compiles in different working directories and requires the resulting binaries to be byte-identical. `--single` is available for quick development builds but is not sufficient for 0B-P1 reproducibility qualification.

Build output is placed below the gitignored `firmware/out/` tree. The builder records:

- upstream and submodule commits;
- source blob pins;
- compiler and Make versions;
- `SOURCE_DATE_EPOCH` derived from the pinned upstream commit;
- artifact size;
- SHA256;
- expected firmware identity;
- reproducibility result.

## Artifact inspection

`firmware/tooling/inspect_artifact.py` validates the built binary without hardware access. It requires:

- a plausible STM32F103 vector table;
- artifact size no larger than 128 KiB;
- reset vector inside the STM32F103 128 KiB application address range;
- exactly one embedded copy of the expected YWD-1278 firmware identity;
- successful SHA256 calculation.

This size/address sanity check does **not** activate flash geometry in `firmware/targets.json`. The target's `flash_enabled`, `firmware_artifact`, and `firmware_sha256` fields remain closed/null until later physical backup/flash/restore qualification.

## 0B-P1 acceptance gate

A candidate 0B-P1 qualification requires all of the following from a clean Raspberry Pi build host with the installer-provided ARM toolchain:

```text
UPSTREAM_PIN=PASS
SUBMODULE_PIN=PASS
YWD1278_BRANDING_TRANSFORM=PASS
BEHAVIORAL_CHANGES=NONE
YWD1278_ARTIFACT_INSPECTION=PASS
ARTIFACT_IDENTITY_COUNT=1
REPRODUCIBILITY=PASS
HARDWARE_ACCESSED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

The artifact SHA256 and toolchain version are then recorded in a dated qualification document and frozen checkpoint. Only after 0B-P1 is frozen do we proceed to protected stock-backup and guarded flash/restore qualification.

## Safety boundary

The build wrapper intentionally contains no device path, GPIO control, systemd manipulation, `stm32flash`, or other hardware programming operation. CI enforces that contract with `tests/firmware_build_contract_test.py`.

Do not manually copy a 0B-P1 artifact into the flash manifest or enable `flash_enabled`. A successful build is not a qualified flash path.
