# YWD-1278 0A-P2 — Stateful appliance installer qualification

Date: 2026-09-02

## Frozen tested code

The exact physically tested installer code is frozen at:

- checkpoint: `checkpoint/0a-p2-stateful-installer-qualified`
- commit: `7eac70e55c3d1ed75e41b30ad5d46addb532ab27`
- product version: `0.1.0-alpha0`

Later `dev` commits may extend installer behavior; they are not implied to be covered by this checkpoint.

## Physical test host

- Raspberry Pi 5 Model B Rev 1.0
- Debian GNU/Linux 13 (trixie)
- Python 3.13.5
- modem UART `/dev/ttyAMA0`
- supported reference MMDVM_HS simplex HAT
- station configuration `KJ6YWD-2`
- configured packet frequency 145.050 MHz

## Observed post-install state

The stateful installer completed successfully with an existing configuration and existing virtual environment. Post-install verification reported:

```text
INSTALLED_VERSION=0.1.0-alpha0
INSTALLED_COMMIT=7eac70e55c3d1ed75e41b30ad5d46addb532ab27
YWD1278_SERVICE_ENABLED=disabled
YWD1278_SERVICE_ACTIVE=inactive
INSTALL_RESUME_SERVICE_ENABLED=disabled
INSTALL_RESUME_SERVICE_ACTIVE=inactive
INSTALL_RESUME_CHECKPOINT=absent
PYTHON_VERSION=3.13.5
YWD1278_VERSION=0.1.0-alpha0
UART_OWNER=none
GPIO20=output-low
GPIO21=output-high
```

The preserved configuration contained:

- callsign `KJ6YWD`
- SSID `2`
- hardware target `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART `/dev/ttyAMA0`
- frequency 145.05 MHz
- KISS `127.0.0.1:8001`
- console `127.0.0.1:8010`
- `tx_enabled = false`
- `allow_automatic_flash = false`

## Qualification conclusions

The physical test qualifies the following behavior at the frozen checkpoint:

- existing configuration is preserved across installer refresh;
- prior station/radio/network values remain intact;
- the installed application/version metadata matches the source being installed;
- the Python environment is valid after the stateful refresh;
- the packet service remains disabled and inactive;
- no stale reboot-resume checkpoint remains after a normal no-reboot-required install;
- the reboot-resume service is disabled/inactive when not needed;
- the HAT control lines finish in the validated application state (BOOT0 low, RESET high);
- the modem UART is released after installation;
- RF transmit remains disabled;
- firmware automatic flashing remains disabled.

The separate reboot/resume oneshot path still requires its own controlled physical qualification. This checkpoint does not claim that path merely because the service was installed and inactive.

## Safety boundary

No RF transmission and no HAT firmware write were part of this qualification. The checkpoint remains a host installer/appliance qualification only.
