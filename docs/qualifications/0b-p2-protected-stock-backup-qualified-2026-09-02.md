# YWD-1278 0B-P2 — protected stock backup and flash geometry qualification

Date: 2026-09-02

Qualifying code boundary before this evidence document:

`7bdd6a79b258efef18628e46efcf16934698ec62`

This qualification records a physical Raspberry Pi 5 + reference simplex MMDVM_HS HAT execution of the YWD-1278 protected two-pass stock backup path.

## Hardware / target

Target:

`mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`

Running application identity before backup:

`MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`

Host:

`Raspberry Pi 5 Model B Rev 1.0`

UART:

`/dev/ttyAMA0`

## Bootloader qualification

Automatic host-control bootloader entry used the physically validated control lines:

- GPIO20 / BOOT0: application low, bootloader high;
- GPIO21 / RESET: explicit low/high reset pulse for bootloader entry;
- no manual HAT button interaction was required.

Observed STM32 factory bootloader identity:

```text
Version      : 0x22
Device ID    : 0x0410 (STM32F10xxx Medium-density)
Flash        : Up to 128KiB
Option RAM   : 16b
STM32_BOOTLOADER_VERSION=0x22
STM32_DEVICE_ID=0x0410
STM32_BOOTLOADER_IDENTITY=PASS
```

The option-byte region was not read.

## Main-flash geometry and backup evidence

The YWD-1278 backup tool read the complete main-flash range twice:

```text
flash base  = 0x08000000
flash bytes = 131072
end address = 0x08020000
```

Both independent reads completed and were byte-identical.

Observed SHA256 for both reads:

`4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`

This exactly matches the previously qualified golden stock image SHA256.

Observed output:

```text
BACKUP_READ_A_SHA256=4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684
BACKUP_READ_B_SHA256=4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684
[ OK ] Two independent 131072-byte reads are byte-identical
[ OK ] Stock main-flash SHA256 matches the qualified golden baseline
```

Protected backup created on the test system:

`/var/lib/ywd-1278/firmware-backups/mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021/20260902-072821`

Its `original-flash.bin` checksum is the exact stock SHA above.

## Return-to-application verification

After the two reads, YWD-1278 returned BOOT0 to the application level and explicitly reset the STM32.

The application then answered with the exact same pre-backup stock identity.

Observed result markers:

```text
HAT_APPLICATION_RESTARTED=YES
STM32_RESET_PULSED=YES
BACKUP_READ_PASSES=2
BACKUP_TWO_PASS_IDENTICAL=YES
GEOMETRY_VERIFIED_BYTES=131072
OPTION_BYTES_READ=NO
BACKUP_CLASS=STOCK
STOCK_SHA256_MATCH=YES
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

## Safety result

Qualified by this test:

- exact application identity gate;
- deterministic GPIO20/21 system-bootloader entry;
- STM32 bootloader version `0x22`;
- STM32 device ID `0x0410`;
- full 128 KiB main-flash geometry;
- two independent full-flash reads;
- byte-for-byte read repeatability;
- exact stock SHA256 match;
- protected target-bound stock rollback backup;
- deterministic return to normal application state;
- exact post-backup stock identity;
- no main-flash writes;
- no option-byte reads;
- no option-byte writes;
- no RF configuration or transmission.

Not qualified by this test:

- writing the 0B-P1 YWD-1278 firmware artifact;
- post-write YWD-1278 identity verification;
- restoring the protected stock image after an actual YWD-1278 write.

Those remain the next guarded round-trip phase.

## Result

```text
YWD1278_0B_P2_PROTECTED_STOCK_BACKUP=PASS
FLASH_GEOMETRY_BYTES=131072
STOCK_SHA256=4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684
TWO_PASS_IDENTICAL=YES
OPTION_BYTES_READ=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```
