# 0B-P3 — Guarded YWD-1278 firmware round-trip qualification

Date: 2026-09-02

Status: **QUALIFIED**

## Scope

This qualification proves that the corrected deterministic 0B-P1R1 YWD-1278 firmware artifact can be programmed into the supported STM32F103 MMDVM_HS HAT, read back exactly, boot successfully, answer the expected MMDVM `GET_VERSION`, and then be replaced by the exact protected 0B-P2 stock image with a full 128 KiB readback and exact stock identity verification.

This is a qualification-only write path. It does **not** enable normal product flashing.

## Tested code boundary

Physical test was run from `dev` code boundary:

`6c415aecf6fb70c6c560e446bc5e77edf46d9dfb`

The post-test manifest/test/documentation commits close the qualification-only write gate and record this evidence. They do not change the physically-tested write/readback sequence.

## Hardware

- Raspberry Pi 5 Model B Rev 1.0
- Supported target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- STM32F103 medium-density
- ADF7021 simplex HAT
- STM32 HSE: 8 MHz
- ADF7021 TCXO: 14.7456 MHz
- UART: `/dev/ttyAMA0`
- GPIO20: STM32 BOOT0
- GPIO21: STM32 RESET
- STM32 system bootloader version: `0x22`
- STM32 device ID: `0x0410`

## Qualified YWD artifact

Artifact:

`firmware/out/0b-p1r1-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Size:

`57316` bytes

SHA256:

`b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8`

Expected identity:

`MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

The corrected P1R1 artifact was previously qualified as deterministic and byte-for-byte reproducible. The historical P1 artifact SHA `db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3` remains revoked because it used the ADF7021 14.7456 MHz TCXO value as the STM32 HSE/OSC value and did not boot successfully.

## Protected stock rollback image

Exact 0B-P2 protected stock image SHA256:

`4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`

Flash geometry:

- base: `0x08000000`
- main flash: `131072` bytes

Exact stock identity:

`MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`

## Physical evidence

The qualification began from the exact stock identity and required explicit `WRITE-YWD-THEN-RESTORE-STOCK` confirmation.

### YWD programming

- expected bootloader version: `0x22` — PASS
- expected device ID: `0x0410` — PASS
- YWD artifact programmed and `stm32flash -v` reported success — PASS
- programmed YWD bytes read back from `0x08000000` for exactly 57316 bytes — PASS
- YWD readback SHA256:
  `b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8`
- readback matched the exact P1R1 artifact — PASS

### YWD runtime identity

After returning BOOT0 low and restarting the STM32 application:

`MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Exact YWD-1278 identity gate — **PASS**

### Exact stock restoration

The HAT was returned to the STM32 system bootloader and the exact protected 131072-byte stock image was programmed.

- stock image write/verify — PASS
- complete 131072-byte restored main flash readback — PASS
- stock restore readback SHA256:
  `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`
- restored main flash matched the exact 0B-P2 stock SHA256 — PASS

After restarting the application, exact stock `GET_VERSION` identity was restored — **PASS**.

Final harness marker:

`YWD1278_0B_P3_ROUNDTRIP=PASS`

## Safety accounting

- Raspberry Pi was not rebooted.
- Network/SSH configuration was not altered.
- RF was not configured by the qualification harness.
- RF was not transmitted.
- STM32 main flash **was intentionally written** as part of this qualification: first the exact P1R1 image, then the exact protected stock image.
- Option-byte writes were forbidden and did not occur.
- Normal product `flash_enabled` remained `false` throughout.
- After qualification, the separate `qualification_write.enabled` gate is returned to `false`.

### Clarification about helper markers

`hat_control.py` prints `FLASH_WRITTEN=NO` because that GPIO helper never performs flash I/O itself. Those lines must not be interpreted as saying that the overall P3 harness performed no flash writes. The P3 harness explicitly invoked `stm32flash` for controlled main-flash writes, and this qualification records `main_flash_write_occurred=true`.

## Result

**0B-P3 QUALIFIED.**

The corrected P1R1 image is now physically runtime-qualified for this target, exact programmed readback is proven, and exact stock round-trip recovery is proven. The generic product flash gate remains closed while development proceeds into the packet-engine port.
