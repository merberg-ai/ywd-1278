# 0B-P11 Packet Firmware Round-Trip Qualification — 2026-09-02

Status: **PHYSICALLY QUALIFIED**

This qualification proves that the exact deterministic YWD-1278 AX25R3 packet firmware artifact from 0B-P10 can be programmed into the supported STM32F103 MMDVM_HS HAT, read back exactly, boot to the exact expected product identity, and then be replaced in the same run by the exact protected stock image with a full-flash readback and exact stock identity verification.

## Hardware / target

- Host: Raspberry Pi 5 Model B Rev 1.0
- Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- MCU: STM32F103 medium density
- STM32 bootloader version: `0x22`
- Device ID: `0x0410`
- Main flash geometry: 131072 bytes at `0x08000000`
- GPIO20: BOOT0
- GPIO21: RESET

## Packet firmware under qualification

Artifact:

`firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Exact properties:

- bytes: `59812`
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- expected GET_VERSION identity: `MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- deterministic build source: frozen engineering commit `d25180ad663d781b761c525d1e699e7b052d6214`
- STM32 HSE: 8 MHz
- ADF7021 TCXO: 14.7456 MHz
- no `OSC=` override

Preflight SHA verification on the target Pi matched the P10 artifact exactly.

## Protected stock recovery image

Backup directory:

`/var/lib/ywd-1278/firmware-backups/mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021/20260902-072821`

Exact stock image:

- bytes: `131072`
- SHA256: `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`
- identity: `MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`

The stock image was previously qualified by two independent full-flash reads in 0B-P2.

## Safety gates

Before writing:

- normal product `flash_enabled=false`;
- historical P3 qualification gate closed;
- dedicated 0B-P11 packet qualification gate enabled;
- exact stock start required;
- exact protected two-pass stock backup required;
- stock restore in the same run required;
- RF configuration forbidden;
- RX start forbidden;
- TX command forbidden;
- option-byte writes forbidden.

The explicit confirmation phrase was:

`WRITE-PACKET-YWD-THEN-RESTORE-STOCK`

The P11 harness contains no application command path other than MMDVM `GET_VERSION`.

## Physical result

The run started from the exact stock GET_VERSION identity.

The STM32 factory bootloader reported:

- version `0x22`;
- device ID `0x0410`.

The exact 59812-byte packet firmware artifact was written and verified by `stm32flash`.

A direct readback of exactly 59812 programmed bytes produced:

`PACKET_READBACK_SHA256=a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`

This exactly matches the 0B-P10 deterministic artifact.

After application restart, the only application command sent was GET_VERSION. The HAT returned exactly:

`MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

The exact protected 131072-byte stock image was then written back in the same run. A complete main-flash readback produced:

`STOCK_RESTORE_READBACK_SHA256=4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`

After restart, the HAT returned the exact original stock identity again.

Final qualification marker:

`YWD1278_0B_P11_PACKET_ROUNDTRIP=PASS`

## Explicit physical observations

- packet artifact exact programmed readback: **PASS**
- packet GET_VERSION runtime identity: **PASS**
- exact stock restore write/verify: **PASS**
- complete 128 KiB stock readback: **PASS**
- final exact stock identity: **PASS**
- main STM32 flash was intentionally written: **YES**
- application commands sent while packet firmware was running: **GET_VERSION only**
- RF configured: **NO**
- RX started: **NO**
- RF transmitted: **NO**
- option bytes written: **NO**

The `FLASH_WRITTEN=NO` markers emitted by `hat_control.py` refer only to that GPIO helper; the P11 harness intentionally performed controlled main-flash writes using `stm32flash`.

## Post-qualification policy

After this proof:

- the AX25R3 product identity is accepted as a physically runnable YWD-1278 identity for this exact target;
- the dedicated P11 qualification write gate is closed again;
- normal product `flash_enabled` remains `false`;
- the HAT remains restored to exact stock firmware at the end of the qualification;
- option-byte writes remain forbidden.

This qualification proves firmware programming/readback/boot identity and safe stock recovery. It does **not** by itself requalify live `YWD_RX` capture or any packet TX path. Those remain separate explicit phases.
