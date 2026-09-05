# Stage H — fresh Raspberry Pi OS from-zero qualification

Date: 2026-09-04  
Timezone: America/Los_Angeles  
Status: **PHYSICALLY QUALIFIED — RX-ONLY PRODUCT APPLIANCE**

## Scope

Stage H proves the normal YWD-1278 product path from a fresh Raspberry Pi OS target through installation, UART repair/reboot/resume, deterministic AX25R4 build, protected stock rollback backup, explicitly authorized firmware deployment, independent programmed readback, guarded service activation, live 145.050 MHz RX, systemd lifecycle, and final reboot/autostart survival.

Stage H grants **no physical TX authority**. TX remained disabled throughout the Stage-H product qualification.

## Product under test

- Hardware: Raspberry Pi 5 Model B Rev 1.0
- OS: Debian GNU/Linux 13 (trixie)
- Architecture: aarch64
- UART: `/dev/ttyAMA0`
- Product frequency: 145.050 MHz
- Installed product commit: `2f5299e65add072fea6ee55a54dc421faf00c276`
- Exact firmware identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- Exact firmware SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`

## Fresh-OS chain physically proven

1. Preinstall audit proved no preexisting YWD-1278 appliance state.
2. The normal installer encountered the expected fresh-OS UART/serial-console condition, repaired it, required a real reboot, and resumed successfully afterward.
3. The packet service remained disabled while the install/firmware prerequisites were incomplete.
4. The exact AX25R4 firmware artifact was deterministically built and hash-qualified.
5. Stock firmware was identified and a protected two-pass 131072-byte rollback backup was captured before any firmware write. Both reads were byte-identical and matched the golden stock SHA256 `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`.
6. The stock-to-AX25R4 main-flash write required explicit `WRITE-FIRMWARE-NOW` confirmation, programmer verification, an independent 59892-byte readback, exact SHA256 match, and exact runtime identity. No option bytes were written.
7. Service eligibility was established before service enablement.
8. Guarded service activation passed with TX disabled and automatic flash disabled.
9. systemd stop/start/restart/SIGTERM cleanup passed; PTY and UART ownership released correctly.
10. Initial live 145.050 MHz RX passed through TCP KISS and both Telnet/PTTY MHEARD surfaces.
11. A final real reboot was proven by kernel boot-ID change.
12. Before the reboot qualifier mutated the service, systemd had automatically returned the enabled/active service plus KISS 8001, Telnet 8010, and `/run/ywd-1278/tnc`.
13. Runtime readiness and firmware/service eligibility revalidated after reboot.
14. A post-reboot stop released the UART; exact AX25R4 identity revalidated with no flash write.
15. After restart, a fresh 65-byte AX.25 frame from `KJ6YWD` on 145.050 MHz was received through KISS and caused fresh MHEARD advancement on both Telnet and PTY surfaces.

## Final reboot evidence

- Pre-reboot boot ID: `79055777-d228-4c3d-9b74-dc27cd322297`
- Post-reboot boot ID: `e39c73d0-797f-4105-b21f-701d866c54bf`
- Boot ID changed: YES
- Pre-reboot MainPID: 4089
- Auto-started MainPID: 1107
- Final MainPID: 1257
- Service auto-start: PASS
- Runtime readiness after reboot: PASS
- Service eligibility after reboot: PASS
- KISS/Telnet/PTTY automatic return: PASS
- UART release after post-reboot stop: PASS
- Exact AX25R4 identity after reboot: PASS
- Fresh post-reboot 145.050 RX: PASS
- Fresh Telnet MHEARD advance: PASS
- Fresh PTY MHEARD advance: PASS

Authoritative evidence: `firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json`.

## Safety result

- TX enabled: NO
- TX command sent by qualifier: NO
- KISS DATA sent by qualifier: NO
- RF transmitted by qualifier: NO
- Firmware write during final reboot qualifier: NO
- Option bytes written during final reboot qualifier: NO
- Automatic firmware flashing: NO

## Boundary after Stage H

Stage H is complete. The next product gate is a **separately staged and explicitly authorized single physical TX acceptance test** at 145.050 MHz. That future gate must not inherit implicit TX authority from Stage H and must preserve the exact AX25R4/installer/runtime evidence frozen here.
