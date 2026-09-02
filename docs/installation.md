# YWD-1278 installation model

YWD-1278 is designed around one user-facing bootstrap command. The bootstrap fetches the selected release/channel and hands control to the full installer; users should not need to manually create a Python environment, install packages, edit Raspberry Pi boot files, or select GPIOs.

## Intended public install

Once the repository is public (or the bootstrap is mirrored on kj6ywd.net), the stable install entry point is intended to be:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/ywd-1278/main/installer/bootstrap.sh | sudo bash
```

Development channel testing may use:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/ywd-1278/dev/installer/bootstrap.sh | sudo bash -s -- --branch dev
```

The repository is currently private, so unauthenticated raw-GitHub curl installation is not expected to work yet. The same bootstrap script can later be hosted unchanged on kj6ywd.net.

## Installer behavior

The full installer:

1. verifies Raspberry Pi / Debian-family platform prerequisites;
2. installs required host and optional firmware-development packages;
3. reuses a compatible existing `/opt/ywd-1278/venv` and refreshes the package in place;
4. rebuilds the venv only when it is absent, uses a different Python major/minor, or an in-place refresh fails;
5. preserves the existing `/etc/ywd-1278/config.toml`;
6. uses existing station, SSID, frequency, UART, KISS-port, and console-port values as setup defaults;
7. audits the Raspberry Pi modem UART and serial-console ownership;
8. performs a read-only supported-HAT probe;
9. if a configured HAT is held in reset, releases only that allowlisted target's application-state GPIOs;
10. on a fresh install, asks once before using a manifest-qualified compatible application-release GPIO candidate after a silent direct probe;
11. installs the systemd units but leaves the packet service disabled while the packet engine/firmware stages remain unqualified;
12. never flashes firmware as a side effect of installation.

## Reboot continuation

Some Raspberry Pi UART corrections require a reboot, such as enabling the primary UART or removing a Linux serial console from the modem UART.

Before rebooting, the installer:

- completes and saves station setup;
- writes a root-only `/var/lib/ywd-1278/install-resume.env` checkpoint;
- installs/enables `ywd-1278-install-resume.service`;
- asks whether to reboot now.

If accepted, the machine is synced and rebooted. On the next boot the oneshot resume service verifies the repaired UART, continues supported-HAT detection, records the detected target in the existing configuration, runs the framework self-test, removes the resume marker, and disables itself. It does not enable the packet service or transmit RF.

If the automatic continuation cannot prove a safe state, it fails closed and leaves the resume marker in place for diagnosis rather than guessing.

## Hardware-control safety

A direct `GET_VERSION` probe is always attempted before any GPIO application-release action. GPIO control is driven by `firmware/targets.json`, not hard-coded into the generic installer.

Fresh-install candidate release requires explicit user authorization. Automatic candidate release is permitted only when all compatible manifest targets agree on one identical host-control profile. Adding a conflicting target therefore disables that automatic path until the ambiguity is resolved.

Application release does not pulse RESET, enter the STM32 bootloader, configure RF, write flash, or touch option bytes.
