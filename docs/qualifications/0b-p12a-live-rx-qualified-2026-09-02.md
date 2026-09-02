# 0B-P12a Live RX Owner/FIFO Qualification — 2026-09-02

Status: **PHYSICALLY QUALIFIED**

This qualification proves that the exact P10/P11-qualified YWD-1278 AX25R3 packet firmware can be activated from exact stock, configured receive-only at 144.390 MHz, run through the bounded single-owner `YWD_RX` FIFO lifecycle on the real HAT, and stop/drain cleanly with no FIFO loss and no packet-transmit activity.

Unlike 0B-P11, successful P12a intentionally leaves the exact packet firmware installed after a final cold restart so the next P12b live over-air packet qualification can proceed without another flash cycle.

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
- RX frequency: `144390000` Hz
- Live RX interval: 3 seconds

## Packet firmware

Artifact:

`firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Exact properties:

- bytes: `59812`
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- exact GET_VERSION identity: `MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- deterministic engineering source: `d25180ad663d781b761c525d1e699e7b052d6214`
- STM32 HSE: 8 MHz
- ADF7021 TCXO: 14.7456 MHz
- no `OSC=` override

## Protected recovery baseline

P12a began from the exact stock identity:

`MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`

Protected stock image:

- bytes: `131072`
- SHA256: `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`
- backup directory: `/var/lib/ywd-1278/firmware-backups/mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021/20260902-072821`

Automatic complete stock recovery remained armed for any failure after the packet image was written.

## Safety gates

Before activation:

- normal product `flash_enabled=false`;
- historical P3 write gate closed;
- historical P11 write gate closed;
- dedicated P12a activation gate enabled;
- exact stock start required;
- exact P10/P11 packet SHA and size required;
- exact protected P2 stock backup required;
- competing modem services required inactive;
- modem UART required free;
- RX configuration/start permitted;
- packet TX command forbidden;
- option-byte writes forbidden.

Explicit confirmation phrase:

`ACTIVATE-PACKET-RX-ONLY`

## Exact firmware activation result

The exact stock start identity passed.

The STM32 factory bootloader reported:

- version `0x22`;
- device ID `0x0410`.

The exact 59812-byte packet image was written and verified by `stm32flash`.

Programmed readback:

`PACKET_READBACK_SHA256=a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`

This exactly matches the P10/P11-qualified packet artifact.

After restart, GET_VERSION returned the exact expected YWD-1278 AX25R3 identity.

## Live single-owner receive result

The physical lifecycle used the product `ModemOwner` and typed receive setup only:

1. GET_VERSION
2. SET_FREQ for 144.390 MHz
3. fixed receive-safe SET_CONFIG
4. YWD_RX START
5. repeated YWD_RX READ and STATUS while continuously draining
6. YWD_RX STOP
7. complete FIFO drain
8. final RX/RF status and diagnostic checks
9. owner close / UART release

Observed counters:

- packed bytes drained: `7210`
- read transactions: `1910`
- status checks: `7`
- initial firmware sample counter: `20`
- final firmware sample counter: `57682`
- samples advanced: `57662`
- peak FIFO available: `4` bytes
- FIFO dropped bytes: `0`
- modem owner transactions: `1926`

Observed state gates:

- active RX flags: `0x0D`
- idle/stopped RX flags: `0x04`
- firmware sample counter advanced: **YES**
- single modem owner: **PASS**
- UART released after owner shutdown: **YES**

## Explicit TX-safety observations

Before and after live RX:

- RF keyups: `0 -> 0`
- RF TX generated samples: `0 -> 0`
- RF TX active: `0`
- packet TX API in the live qualification path: **ABSENT**
- RF receive configured: **YES**
- RF transmitted: **NO**
- option bytes written: **NO**

The repeated `FLASH_WRITTEN=NO` marker from `hat_control.py` refers only to the GPIO helper. P12a intentionally wrote STM32 **main flash** through `stm32flash` while option-byte writes remained forbidden.

## Final state

After the live lifecycle passed:

- `YWD1278_P12A_LIVE_RX_OWNER=PASS`
- `YWD1278_0B_P12A_PACKET_LIVE_RX=PASS`
- exact packet firmware remained installed: **YES**
- packet firmware was cold-restarted: **YES**
- exact packet identity was verified after final restart: **YES**
- modem UART released: **YES**
- normal product flashing remained disabled: **YES**
- P3 gate remained closed: **YES**
- P11 gate remained closed: **YES**
- P12a activation gate is closed in the post-qualification manifest
- packet TX remains unqualified and unavailable through this receive-only path
- option-byte writes remain forbidden

## Qualification boundary

P12a proves the real packet firmware activation and live receive-only HAT transport/FIFO layer. It does **not** yet prove that a new live over-air Bell-202 AX.25 packet is decoded and delivered through the assembled product runtime to TCP KISS.

That end-to-end live receive proof is 0B-P12b:

`RF packet -> ADF7021 / YWD_RX -> streaming Bell-202 -> AX.25 event -> TCP KISS`
