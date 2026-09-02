# YWD-1278

**YWD-1278** is a modern AX.25 packet TNC/node for Raspberry Pi systems fitted with a compatible MMDVM_HS-style radio HAT.

The project is inspired by classic hardware TNCs such as the MFJ-1278/TNC2 family: familiar command-mode operation, KISS support, monitor mode, connected AX.25, beaconing, heard lists, and packet-node features — rebuilt as a modern Linux appliance.

## Project status

YWD-1278 is in early development. There is no stable release or flashable image yet.

The initial implementation is being built from the physically qualified AX.25 RX/TX/KISS work developed in `merberg-ai/ywd-mmdvm`. The frozen engineering reference for the product foundation is:

- repository: `merberg-ai/ywd-mmdvm`
- checkpoint: `checkpoint/ax25-bidirectional-tnc-foundation`
- qualification evidence commit: `d25180ad663d781b761c525d1e699e7b052d6214`

## Goals

- Bell-202 / 1200-baud AX.25 RX and TX using the MMDVM HAT RF hardware directly
- standard KISS over TCP and virtual serial/PTY interfaces
- classic TNC-style command console over local terminal and Telnet
- connected-mode modulo-8 AX.25
- monitor mode, MHEARD, frame logging, and diagnostics
- UNPROTO and configurable beaconing
- bounded CSMA / p-persistence channel access
- packet-node / mailbox features
- GitHub-based install/update workflow
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

Do not treat development firmware as a generic MMDVM_HS image. Firmware support will be allowlisted by known hardware targets and must pass validation before flashing.

## Installation

GitHub installation is planned for the first development releases. A flashable Raspberry Pi image will come later, after the software/firmware stack is stable.

The installer will eventually handle:

- Raspberry Pi and HAT detection
- dependencies
- UART configuration
- conflicting modem-service detection
- YWD-1278 service installation
- configuration creation
- firmware compatibility checks
- protected firmware backup
- firmware flashing and verification
- rollback / stock restoration tooling

## Licensing

YWD-1278 contains original host-side work plus firmware work derived from `MMDVM_HS`. Firmware-derived code must retain the applicable upstream GPL notices and attribution. See `LICENSING.md` on the development branch for the exact source/attribution policy as the port is assembled.

## Safety

Firmware flashing can make a HAT temporarily unusable if the wrong target is selected or power is interrupted. YWD-1278's flash tooling is being designed to fail closed: unknown hardware, mismatched firmware identity, unavailable recovery path, or failed verification should stop the operation rather than guess.

---

YWD-1278 is not affiliated with MFJ Enterprises. The name describes the project's classic-TNC inspiration; compatibility goals will be documented explicitly rather than implying byte-for-byte MFJ emulation.
