# YWD-1278 0A-P4a — installer resume state machine qualification

Date: 2026-09-02

This qualification records a physical Raspberry Pi 5 execution of the YWD-1278 installer resume state machine using the real `ywd-1278-install-resume.service`, started manually rather than by an actual reboot.

## Scope

Qualified:

- root-owned resume checkpoint was read successfully;
- Raspberry Pi UART audit passed;
- serial console absence was verified;
- supported HAT detection passed;
- exact stock firmware identity was detected and classified as `STOCK`;
- existing configuration was bound to the detected HAT target;
- framework self-test passed;
- resume checkpoint was removed after success;
- resume service disabled itself and became inactive;
- packet service remained disabled;
- no RF transmission occurred;
- no firmware flash write occurred;
- no option-byte write occurred.

Not qualified by this test:

- systemd launching the resume service automatically during an actual reboot;
- boot ordering under an unattended cold boot;
- cold-boot GPIO recovery inside the resume service during this exact test, because the HAT was already in normal application state when the service was started.

Those behaviors remain separate from this qualification. Cold-boot HAT application-state recovery was previously physically qualified in 0A-P1.

## Physical evidence

Observed service state after completion:

```text
disabled
inactive
Resume checkpoint cleared
```

Resume journal included:

```text
RUNTIME_UART_READY=YES
SERIAL_CONSOLE_PRESENT=NO
REBOOT_REQUIRED=NO
REBOOT_REASONS=none
HAT_DETECT=PASS
DETECTED_TARGET=mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021
DETECTED_IDENTITY=MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed
FIRMWARE_CLASS=STOCK
FIRMWARE_DESCRIPTION=Recognized stock MMDVM_HS firmware
APPLICATION_RELEASE_USED=NO
RF_CONFIGURED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
YWD1278_FRAMEWORK_SELF_TEST=PASS
MODEM_UART_OPENED=NO
RF_TRANSMITTED=NO
YWD1278_INSTALL_RESUME=PASS
```

systemd reported the oneshot deactivated successfully and finished normally.

## Result

```text
YWD1278_0A_P4A_RESUME_STATE_MACHINE=PASS
AUTOMATIC_BOOT_LAUNCH_QUALIFIED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

This checkpoint proves the resumable installer logic itself without claiming an unattended-reboot qualification that was not physically exercised.
