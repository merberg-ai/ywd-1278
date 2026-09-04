# Fresh-install Stage G — existing-Pi reboot survival qualified

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage G is **physically complete on the existing Raspberry Pi for RX-only installed-appliance operation, including reboot survival**.

The installed product under test remained the exact candidate installed earlier:

- installed commit: `5cb6e072c61d00376c1c46db7832912d71cace26`
- target: Raspberry Pi 5 Model B Rev 1.0
- OS: Debian GNU/Linux 13 (trixie)
- UART: `/dev/ttyAMA0`
- frequency: 145.050 MHz
- TX: disabled
- automatic flash: disabled
- firmware identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

The reboot qualification harness was checked out at `2e5bcefb8f988c2366dc4d58cdc021c634a6f929`. This later checkout added evidence/reboot tooling and did not reinstall or mutate the product runtime under `/opt/ywd-1278`.

## Reboot proof

The pre-reboot kernel boot ID was:

`74906ed4-3611-41d6-a194-b749088597c5`

The post-reboot kernel boot ID was:

`975c108c-2989-4904-8df3-d716649ae3a4`

They differ, proving a real reboot occurred.

Before the post-reboot qualifier performed any service start/restart action, it observed:

- service still enabled;
- service already active;
- auto-started MainPID `1771`;
- PTY automatically present;
- loopback KISS port 8001 reachable;
- loopback Telnet port 8010 reachable;
- runtime readiness still `READY`;
- Stage-F service eligibility still valid;
- TX still disabled;
- automatic flash still disabled.

## Post-reboot trust and lifecycle proof

The qualifier then intentionally stopped the product service and proved:

- UART ownership released;
- PTY removed;
- exact AX25R4 target/identity still detected directly from the HAT;
- no flash write occurred;
- no RF TX occurred.

After restarting the service, KISS and Telnet returned and the service remained enabled/active.

## Fresh post-reboot RX proof

A new packet was generated on 145.050 MHz after the post-reboot MHEARD baseline was captured.

Observed result:

- KISS frame length: 36 bytes;
- AX.25 source: `KJ6YWD-5`;
- KISS DATA received: yes;
- Telnet MHEARD fresh COUNT/LAST_NS advance: yes;
- PTY MHEARD fresh COUNT/LAST_NS advance: yes;
- no KISS DATA sent by qualifier;
- no TX command sent;
- qualifier did not open the modem UART;
- qualifier transmitted no RF.

Final product service state was enabled and active with MainPID `2660`.

## Qualified Stage-G claims

Stage G now physically proves on the existing Pi:

1. normal installed-appliance runtime with TX disabled;
2. protected stock rollback trust and exact AX25R4 programmed readback/identity without unnecessary rewrite;
3. guarded service activation;
4. systemd stop/start/restart/SIGTERM cleanup;
5. UART and PTY release on stop;
6. live 145.050 MHz RX to TCP KISS;
7. Telnet and PTY MHEARD correlation;
8. actual reboot survival;
9. automatic service startup after reboot;
10. readiness/eligibility persistence and revalidation after reboot;
11. fresh post-reboot 145.050 MHz KISS RX and fresh Telnet/PTTY MHEARD advancement.

## Explicitly not qualified by Stage G

- physical RF TX from the product appliance;
- KISS DATA TX acceptance;
- fresh Raspberry Pi OS from-zero installation;
- fresh-OS UART repair/reboot/resume path;
- fresh-OS stock-firmware backup/write path;
- 0F UNPROTO/converse/beaconing;
- 0G connected mode.

Physical TX remains a separate explicit authorization gate after the fresh-OS RX/install proof.
