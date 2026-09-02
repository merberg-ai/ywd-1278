# YWD-1278 0A-P1 Qualification — Clean Install + Stock HAT Probe

Date: 2026-09-02

Status: **QUALIFIED**

Qualifying code boundary before this evidence document:

```text
8bfc75fc00edff59840a127c74a7cd765760f5c2
systemd: release configured HAT before daemon start
```

## Scope

This qualification proves the initial YWD-1278 appliance framework can be installed onto the clean Raspberry Pi 5 test host, remain disabled/inactive, recover the supported HAT from the Pi's cold-boot GPIO state using only the explicitly configured allowlisted target, and identify the exact stock MMDVM_HS firmware without RF configuration or firmware writes.

It does **not** qualify packet RX/TX, KISS runtime operation, firmware flashing, automatic boot enablement, or option-byte operations.

## Clean host state

Before YWD-1278 testing, the prior YWD-MMDVM packetd/lab runtime had been removed from systemd/runtime state. The modem UART was free and no YWD/KISS listeners or packet-radio processes were active.

YWD-1278 setup was completed with:

```text
Station:   KJ6YWD-2
Frequency: 145.050 MHz
UART:      /dev/ttyAMA0
KISS:      127.0.0.1:8001
Console:   127.0.0.1:8010
TX:        disabled
```

The installed service remained:

```text
ywd-1278.service enabled: disabled
ywd-1278.service active:  inactive
UART owner:               none
```

## Cold-boot HAT control-state observation

After a real reboot, before any manual GPIO correction or YWD-1278 probe:

```text
20: a2    pn | lo // GPIO20 = I2S0_SDI0
21: a2    pn | lo // GPIO21 = I2S0_SDO0
```

The supported reference HAT uses Pi GPIO20 as STM32 BOOT0 and GPIO21 as STM32 RESET. In this cold-boot state the STM32 did not answer MMDVM `GET_VERSION` because RESET was effectively held low.

## Target-aware application release

YWD-1278 was configured for the allowlisted target:

```text
mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
```

Running the read-only probe caused YWD-1278 to use the target's qualified host-control definition to place the HAT into normal application state without pulsing reset:

```text
HAT_CONTROL_TARGET=mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
HAT_CONTROL_HOST=Raspberry Pi 5 Model B Rev 1.0
HAT_CONTROL_BOOT0_BEFORE=20: a2    pn | lo // GPIO20 = I2S0_SDI0
HAT_CONTROL_RESET_BEFORE=21: a2    pn | lo // GPIO21 = I2S0_SDO0
HAT_CONTROL_BOOT0_AFTER=20: op dl pn | lo // GPIO20 = output
HAT_CONTROL_RESET_AFTER=21: op dh pn | hi // GPIO21 = output
HAT_APPLICATION_STATE_RELEASED=YES
STM32_RESET_PULSED=NO
MODEM_UART_OPENED=NO
RF_CONFIGURED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
HAT_APPLICATION_RELEASE_USED=YES
```

The behavior is fail-closed: GPIO control is tied to the explicitly configured allowlisted hardware target rather than being applied generically to an unknown board.

## Exact stock identity

After application-state release, the same probe successfully obtained the stock application identity:

```text
HAT_DEVICE=/dev/ttyAMA0
HAT_IDENTITY=MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed
HAT_TARGET_MATCH=mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
HAT_TARGET_IDENTITY=PASS
RF_CONFIGURED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

This is the exact stock identity preserved in the original YWD-MMDVM hardware baseline.

## Acceptance result

```text
CLEAN_INSTALL_FRAMEWORK=PASS
SERVICE_DISABLED=PASS
SERVICE_INACTIVE=PASS
UART_FREE_BEFORE_PROBE=PASS
COLD_BOOT_RESET_LOW_REPRODUCED=PASS
ALLOWLISTED_TARGET_CONTROL=PASS
BOOT0_APPLICATION_LEVEL=PASS
RESET_RELEASE_LEVEL=PASS
STM32_RESET_PULSED=NO
STOCK_GET_VERSION=PASS
STOCK_IDENTITY_EXACT=PASS
RF_CONFIGURED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
YWD1278_0A_P1=PASS
```

## Qualification boundary

This checkpoint establishes a clean physical product baseline for YWD-1278:

```text
clean Raspberry Pi 5
    -> YWD-1278 framework installed
    -> service remains disabled/inactive
    -> explicit supported HAT target configured
    -> cold-boot BOOT0/RESET state recovered safely
    -> exact stock HAT identity obtained
    -> no RF configuration
    -> no flash writes
    -> no option-byte writes
```

Future packet-engine and firmware work must preserve these fail-closed hardware-selection and no-unintended-write properties.
