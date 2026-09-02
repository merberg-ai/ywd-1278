# YWD-1278 0A-P3 — HAT / firmware discovery UX qualification

Date: 2026-09-02

## Scope

Physical qualification of the installer/setup read-only hardware and firmware discovery path on the reference Raspberry Pi 5 + simplex STM32F103/ADF7021 MMDVM_HS HAT.

This qualification does **not** enable the packet service, configure RF, transmit RF, enter the STM32 bootloader, write flash, or write option bytes.

## Reference hardware

- Host: Raspberry Pi 5 Model B Rev 1.0
- Modem UART: `/dev/ttyAMA0`
- HAT target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- HAT firmware before test: exact stock MMDVM_HS identity

## Read-only detector evidence

The physical detector returned:

```text
HAT_DETECT=PASS
DETECTED_TARGET=mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
DETECTED_IDENTITY=MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed
FIRMWARE_CLASS=STOCK
FIRMWARE_DESCRIPTION=Recognized stock MMDVM_HS firmware
APPLICATION_RELEASE_USED=NO
RF_CONFIGURED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

The already-released HAT therefore required no GPIO action during this detector run.

## Setup UX evidence

Interactive setup automatically incorporated the detected hardware and firmware status and showed the persisted operator configuration as defaults. The accepted configuration summary was:

```text
Station: KJ6YWD-2
Hardware: mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
Current HAT firmware: STOCK — MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed
UART: /dev/ttyAMA0
Frequency: 145.05 MHz
KISS: 127.0.0.1:8001
Console: 127.0.0.1:8010
```

Setup backed up the prior configuration, wrote the accepted configuration, and explicitly reported that RF transmit remained disabled.

## Classification safety behavior

Firmware identity handling is intentionally separated from HAT silence:

- exact manifest stock identity -> `STOCK`
- YWD-1278 identity prefix -> `YWD1278`
- known prior YWD engineering identity -> `YWD_ENGINEERING`
- other known manifest identity -> `KNOWN_OTHER`
- valid responding but unrecognized identity -> `UNKNOWN`
- ambiguous manifest match -> `AMBIGUOUS`

A valid but unknown GET_VERSION response is not treated as a silent HAT and therefore does not by itself authorize GPIO recovery.

## Acceptance

- `HAT_DETECT=PASS`
- exact stock identity read successfully
- supported target matched uniquely
- firmware classified as `STOCK`
- setup displayed current firmware state to the operator
- existing station/radio/network defaults were preserved
- configuration backup created before write
- `tx_enabled=false`
- `RF_CONFIGURED=NO`
- `FLASH_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

**Result: YWD-1278 0A-P3 HAT / firmware discovery UX — QUALIFIED.**
