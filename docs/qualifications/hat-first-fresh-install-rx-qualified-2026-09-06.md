# HAT-first installer — fresh install, reboot, and live-RX qualification

Date: 2026-09-06  
Timezone: America/Los_Angeles  
Status: **PHYSICALLY QUALIFIED — RX-ONLY PRODUCT APPLIANCE**

## Scope

This qualification proves the streamlined HAT-first YWD-1278 product installer on a fresh Raspberry Pi target using the public `dev` bootstrap. It covers Raspberry Pi preparation, required UART repair/reboot, interactive HAT qualification before station configuration, deterministic AX25R4 preparation, protected stock rollback backup, explicitly authorized firmware installation, independent programmed readback, exact runtime identity, station configuration, service eligibility, RX-safe systemd activation, live 145.050 MHz receive through the normal product daemon, and reboot/autostart survival.

This qualification grants **no physical TX authority**. RF transmit remained disabled throughout.

## Product under test

- Hardware: Raspberry Pi 5 Model B Rev 1.0
- OS: Debian GNU/Linux 13 (trixie)
- Architecture: aarch64
- Installed product commit: `b10bae526c9f21ee36d6531dfbb44feb0816fd24`
- Station: `KJ6YWD-10`
- Product frequency: 145.050 MHz
- UART: `/dev/ttyAMA0`
- TCP KISS: `127.0.0.1:8001`
- Classic Telnet console: `127.0.0.1:8010`
- PTY link: `/run/ywd-1278/tnc`
- Hardware target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- Stock identity before deployment: `MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`
- Qualified product identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- Qualified firmware SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- Qualified stock SHA256: `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`

## Qualification lineage note

An immediately preceding installer candidate, commit `37c4518dba1b0980a1d9ab72c25a745bc8684f45`, exposed a human-output `record_marker()`/`set -e` control-flow bug. That attempt terminated immediately after recording `SOURCE_COMMIT`, before Stage 1, UART/HAT access, firmware preparation, firmware write, or RF activity. The bug was fixed and regression-tested before the successful qualification candidate `b10bae526c9f21ee36d6531dfbb44feb0816fd24` was installed.

## HAT-first chain physically proven

1. The public `dev` bootstrap installed the exact candidate commit `b10bae526c9f21ee36d6531dfbb44feb0816fd24`.
2. The installer detected the expected fresh-system UART/serial-console condition, removed Linux serial-console ownership, staged the UART repair, and required a real reboot.
3. Boot-time resume only verified platform/UART readiness. It did not perform HAT setup, station configuration, firmware write, service enablement, or RF TX.
4. Interactive resume continued at HAT qualification with the radio UART ready.
5. The installer positively detected the supported HAT and classified the exact running firmware as recognized stock.
6. The exact AX25R4 firmware was deterministically built and verified at 59892 bytes with SHA256 `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`.
7. Before any firmware write, the installer entered the expected STM32 bootloader (`0x22`, device `0x0410`) and captured two independent 131072-byte main-flash reads. The reads were byte-identical and both matched stock SHA256 `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`.
8. The original stock application was returned to application mode and its exact identity revalidated before programming.
9. After explicit operator confirmation, AX25R4 was programmed. The programmed region was independently read back and matched SHA256 `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`.
10. The HAT returned to application mode with the exact qualified YWD-1278 AX25R4 runtime identity.
11. The installer wrote `HARDWARE-QUALIFIED` evidence while service eligibility remained false, proving HAT qualification was completed before station/runtime configuration.
12. Station setup then configured `KJ6YWD-10`, 145.050 MHz, `/dev/ttyAMA0`, KISS port 8001, console port 8010, and `/run/ywd-1278/tnc`. RF transmit remained disabled.
13. Full runtime readiness passed, hardware evidence was promoted to service eligibility, and the normal packet service was enabled and started in RX-safe mode.
14. Final activation evidence reported `SERVICE_ENABLED=YES`, `SERVICE_ACTIVE=YES`, `TX_ENABLED=NO`, `AUTOMATIC_FLASH=NO`, `FLASH_WRITTEN=NO`, and `RF_TRANSMITTED=NO`.

## Initial live-RX evidence

The normal installed `ywd1278d` product daemon received real packet traffic on 145.050 MHz with no special qualification harness.

A TCP KISS RX-only client received an AX.25 frame with:

- source: `KJ6YWD-5`
- destination: `KE6CHO-5`
- path: DIRECT
- control: `0xD1`
- raw AX.25: `968a6c86909eea96946cb2ae886bd1`

The classic console then reported:

- `STATUS OK`
- `HEALTH OK`
- `PROBLEMS NONE`
- `decoded_rx_frames=5`
- `rows_written=5`
- `MHEARD frame_count=5`
- `tx_dispatches=0`
- `tx_dispatched=0`
- `data_admitted=0`
- `kiss_messages_received=0`
- TX queue depth `0`

MHEARD contained both direct `KJ6YWD-5` traffic and `KJ6YWD` traffic heard via the packet network.

## Reboot/autostart evidence

A subsequent ordinary system reboot proved systemd lifecycle and automatic appliance return:

- `ywd-1278.service`: enabled
- `ywd-1278.service`: active
- auto-started MainPID: `1113`
- KISS listener returned at `127.0.0.1:8001`
- Telnet listener returned at `127.0.0.1:8010`
- PTY link returned as `/run/ywd-1278/tnc -> /dev/pts/0`
- exact AX25R4 firmware identity returned
- daemon reported `PRODUCT_TX=DISABLED`
- daemon reported `CLASSIC_0F=TX-DISABLED`
- forwarding remained disabled

The first post-reboot console check already showed fresh RF receive activity:

- `decoded_rx_frames=2`
- `rows_written=2`
- `HEALTH OK`
- `tx_dispatches=0`
- `tx_dispatched=0`

After additional real 145.050 MHz traffic, the same boot advanced to:

- `decoded_rx_frames=5`
- `rows_written=5`
- persistent `MHEARD frame_count=11`
- `HEALTH OK`
- `PROBLEMS NONE`
- `tx_dispatches=0`
- `tx_dispatched=0`
- `data_admitted=0`
- TX queue depth `0`

The post-reboot MHEARD database advanced with `KJ6YWD` direct traffic to destination `JIM` and retained the previously heard `KJ6YWD-5 -> KE6CHO-5` direct traffic.

`RETENTION_PLAN UNAVAILABLE` remained an informational absent diagnostics source; the runtime health authority still reported `STATUS OK`, `HEALTH OK`, and `PROBLEMS NONE`.

## Safety result

- Product TX enabled: NO
- Classic 0F TX authority: DISABLED
- KISS DATA submitted by qualifier: NO
- TX dispatches observed: 0
- TX queue admissions observed: 0
- RF transmitted by installer/qualifier: NO
- Automatic firmware flashing: NO
- Option bytes written: NO
- Firmware write during reboot/autostart qualification: NO

## Result

**PASS.** The HAT-first installer is physically qualified for the tested Pi 5 / Debian 13 / supported simplex MMDVM_HS HAT combination through fresh setup, guarded stock-to-AX25R4 deployment, service activation, live normal-daemon receive on 145.050 MHz, and reboot/autostart recovery, with RF transmit disabled throughout.

Authoritative operator evidence: `/var/log/ywd-1278/install.log` captured during installation plus the live KISS/classic-console and post-reboot terminal transcripts from the physical target.

## Boundary after this qualification

This qualification freezes the streamlined HAT-first fresh-install and RX-only appliance path at installed product commit `b10bae526c9f21ee36d6531dfbb44feb0816fd24`. It does **not** grant or imply physical TX authority. Any later TX acceptance remains a separately staged and explicitly authorized physical qualification.
