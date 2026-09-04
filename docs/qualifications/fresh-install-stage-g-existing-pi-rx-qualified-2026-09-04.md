# Fresh-install Stage G — existing-Pi installed-appliance RX qualification

Date: 2026-09-04 (America/Los_Angeles)

## Result

The existing Raspberry Pi installed-appliance rehearsal is **physically qualified through RX and console operation**. Reboot survival remains a separate pending Stage-G gate. Physical TX remains prohibited.

Tested candidate:

- host-staged checkpoint: `checkpoint/product-existing-pi-stage-g-host-staged`
- tested source SHA: `5cb6e072c61d00376c1c46db7832912d71cace26`
- target: Raspberry Pi 5 Model B Rev 1.0
- OS: Debian GNU/Linux 13 (trixie)
- HAT: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- exact runtime identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

## Exact checkout and normal installer

The target checked out the exact host-staged SHA with a clean worktree using the PuTTY-safe child-shell wrapper. The wrapper returned zero and the parent PuTTY session remained alive.

The normal product installer then passed on the real Pi:

- installed commit: `5cb6e072c61d00376c1c46db7832912d71cace26`
- UART audit: runtime-ready, no serial console, no reboot required
- HAT detection: exact supported target and exact AX25R4 product identity
- station: `KJ6YWD-10`
- frequency: 145.050 MHz
- UART: `/dev/ttyAMA0`
- KISS: `127.0.0.1:8001`
- Telnet console: `127.0.0.1:8010`
- PTY: `/run/ywd-1278/tnc`
- runtime readiness: READY
- TX disabled
- automatic flash disabled
- service still disabled after installation
- no RF TX and no flash write during installation

## Exact AX25R4 artifact

The deterministic product firmware preparation built twice reproducibly and produced:

- size: `59892` bytes
- SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- exact embedded product identity count: 1
- no hardware access, flash write, option-byte write, or RF TX during preparation

## Physical Stage-F firmware trust

The Stage-F deployment gate ran against the real HAT with TX disabled.

It verified the protected stock rollback backup at:

`/var/lib/ywd-1278/firmware-backups/mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021/20260902-072821`

with:

- stock SHA256: `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`
- two verified read passes
- no option-byte operation

Because the exact qualified AX25R4 identity was already running, **no main-flash rewrite occurred**. The gate entered the STM32 bootloader only for programmed-byte verification, confirmed bootloader version `0x22` and device ID `0x0410`, read back exactly the qualified image region, and obtained the exact AX25R4 SHA256. It then restarted the application and re-established the exact runtime identity.

The resulting service-eligibility record passed and the service remained disabled at the end of Stage F.

## Guarded Stage-G service activation

`installer/enable-product-service.sh` revalidated Stage-F eligibility, exact installed commit, safe configuration, free UART, target identity, and exact live AX25R4 identity before it enabled/started the product service.

Result:

- service eligibility: PASS
- service enabled: YES
- service active: YES
- initial MainPID: `143317`
- TX disabled
- automatic flash disabled
- no flash write
- no RF TX

## Systemd / SIGTERM / ownership lifecycle

The RX-only Stage-G lifecycle qualifier passed:

- `systemctl stop`: PASS
- graceful SIGTERM cleanup: PASS
- PTY cleanup after stop: PASS
- UART release after stop: PASS
- stopped MainPID: `143317`
- `systemctl start`: PASS, MainPID `143366`
- `systemctl restart`: PASS, replacement MainPID `143398`
- loopback KISS port 8001: PASS
- loopback Telnet port 8010: PASS

## Live 145.050 MHz RX

With the installed service running, a real known packet was generated on 145.050 MHz.

The installed appliance produced:

- console HEALTH: PASS
- KISS DATA received: YES
- AX.25 frame length: `69` bytes
- decoded source: `KJ6YWD`
- Telnet `MHEARD` source match: YES
- PTY `MHEARD` source match: YES
- qualifier TX command sent: NO
- qualifier KISS DATA sent: NO
- qualifier modem UART open: NO
- qualifier RF TX: NO

This physically proves the installed path through live RF receive, the AX25R4 HAT, Pi-side packet decode/runtime, TCP KISS, MHEARD storage/observation, Telnet console, and PTY console on the real existing Pi.

## Evidence boundary

This qualification **does not yet claim reboot survival**. The physical run explicitly ended with `REBOOT_QUALIFICATION=PENDING`.

It also does not authorize or qualify:

- KISS DATA transmit;
- any RF TX;
- fresh Raspberry Pi OS installation;
- 0F UNPROTO/converse/beaconing;
- 0G connected mode.

## Next gate

Record the current kernel boot ID, reboot the Pi, and require the enabled service to return automatically with the same exact installed commit and no-TX configuration. Then verify post-boot KISS/Telnet/PTTY availability, graceful UART release for an exact AX25R4 identity recheck, service restart, and one fresh 145.050 MHz packet reaching KISS plus both MHEARD surfaces.
