# YWD-1278

**YWD-1278** is a modern AX.25 packet TNC/node for Raspberry Pi systems fitted with a compatible MMDVM_HS-style radio HAT.

The project is inspired by classic hardware TNCs such as the MFJ-1278/TNC2 family: familiar command-mode operation, KISS support, monitor mode, connected AX.25, beaconing, heard lists, and packet-node features — rebuilt as a modern Linux appliance.

## Project status

YWD-1278 is in early development. There is no stable firmware release or flashable image yet.

The initial implementation is being built from the physically qualified AX.25 RX/TX/KISS work developed in `merberg-ai/ywd-mmdvm`. The frozen engineering reference for the product foundation is:

- repository: `merberg-ai/ywd-mmdvm`
- checkpoint: `checkpoint/ax25-bidirectional-tnc-foundation`
- qualification evidence commit: `d25180ad663d781b761c525d1e699e7b052d6214`

The first physical YWD-1278 host milestone is also qualified: clean framework installation, cold-boot HAT application-state recovery, and exact stock-firmware identity detection with no RF configuration or firmware writes. See `docs/qualifications/0a-p1-clean-install-stock-hat-qualified-2026-09-02.md`.

## Goals

- Bell-202 / 1200-baud AX.25 RX and TX using the MMDVM HAT RF hardware directly
- standard KISS over TCP and virtual serial/PTY interfaces
- classic TNC-style command console over local terminal and Telnet
- connected-mode modulo-8 AX.25
- monitor mode, MHEARD, frame logging, and diagnostics
- UNPROTO and configurable beaconing
- bounded CSMA / p-persistence channel access
- packet-node / mailbox features
- one-command GitHub/site install and update workflow
- safe, target-validated firmware flashing and stock-firmware recovery
- later: polished WebUI and flashable Raspberry Pi image

## Architecture

The Raspberry Pi is the TNC brain. The HAT firmware is deliberately kept focused on the physical RF/modem boundary.

```text
Applications / TNC console / KISS / node
                  |
          AX.25 + CSMA + logging
                  |
        Bell-202 encode/decode on Pi
                  |
        single-owner modem service
                  |
                UART
                  |
       MMDVM HAT STM32 + ADF7021
                  |
                 RF
```

A core design rule is that **exactly one process owns the modem UART**. KISS clients, command sessions, beaconing, connected-mode sessions, logging, and future node services all operate through the central packet engine.

## Branches

- `main` — stable project landing branch and known-good milestones
- `dev` — active development
- `checkpoint/*` — frozen qualification boundaries

Do not treat development firmware as a generic MMDVM_HS image. Firmware support is allowlisted by known hardware targets and must pass validation before flashing.

## Installation

YWD-1278 now has a standalone bootstrap intended to become the single user-facing install entry point. Once the repository is public (or the same bootstrap is mirrored on kj6ywd.net), stable installation is intended to be one pasted command:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/ywd-1278/main/installer/bootstrap.sh | sudo bash
```

For development-channel testing once raw access is available:

```bash
curl -fsSL https://raw.githubusercontent.com/merberg-ai/ywd-1278/dev/installer/bootstrap.sh | sudo bash -s -- --branch dev
```

While the repository is private, use an authenticated checkout and run:

```bash
git clone -b dev https://github.com/merberg-ai/ywd-1278.git
cd ywd-1278
sudo ./installer/install.sh
```

The installer handles dependencies, preserves existing configuration, reuses a compatible Python venv, audits the Raspberry Pi UART, attempts supported-HAT detection, and can safely repair UART/serial-console boot settings. If a repair requires reboot, it saves a root-only checkpoint, offers to reboot, and continues automatically on the next boot through a temporary oneshot service.

Existing callsign, SSID, frequency, UART, KISS-port, and console-port values become the defaults on later installer runs. Firmware is **never flashed as an installer side effect**, and the packet service remains disabled until its packet-engine/firmware stage is qualified.

See `docs/installation.md` for the installer state machine and safety model.

## Licensing

YWD-1278 contains original host-side work plus firmware work derived from `MMDVM_HS`. Firmware-derived code must retain the applicable upstream GPL notices and attribution. See `LICENSING.md` on the development branch for the exact source/attribution policy as the port is assembled.

## Safety

Firmware flashing can make a HAT temporarily unusable if the wrong target is selected or power is interrupted. YWD-1278's flash tooling is being designed to fail closed: unknown hardware, mismatched firmware identity, unavailable recovery path, or failed verification should stop the operation rather than guess.

---

YWD-1278 is not affiliated with MFJ Enterprises. The name describes the project's classic-TNC inspiration; compatibility goals will be documented explicitly rather than implying byte-for-byte MFJ emulation.
