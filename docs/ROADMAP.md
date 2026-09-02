# YWD-1278 Roadmap

## 0A — Product framework

- [x] main landing README
- [x] dev branch
- [x] product package/version skeleton
- [x] safe example configuration
- [x] colorized install/setup/uninstall framework
- [x] systemd service candidate
- [x] fail-closed firmware target manifest
- [x] read-only HAT identity probe
- [x] protected flash/stock-restore framework
- [x] YWD-MMDVM porting manifest
- [x] clean Raspberry Pi install/framework qualification (0A-P1)
- [x] stateful appliance installer/update qualification (0A-P2)
- [x] supported-HAT + firmware discovery/setup UX qualification (0A-P3)
- [x] installer resume state-machine qualification (0A-P4a)
- [ ] unattended real-boot resume launch field test — deferred until physical recovery access is available; tracked in issue #1 and does not block 0B

## 0B — Qualified packet engine port

- [x] 0B-P1 deterministic `YWD-1278`-branded build reproducibility — historical checkpoint retained, but its artifact is **revoked for runtime use** because the build incorrectly passed the ADF7021 14.7456 MHz TCXO as the STM32 HSE/OSC value
- [x] 0B-P1R1 corrected deterministic branded build using pinned upstream MMDVM_HS_Hat recipe: STM32 HSE default 8 MHz, ADF7021 TCXO 14.7456 MHz, no OSC override; qualified SHA256 `b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8`
- [x] establish exact first supported target flash geometry/hash (0B-P2)
- [x] qualify protected two-pass stock backup (0B-P2)
- [x] guarded YWD-1278 flash/restore round trip (0B-P3) — corrected P1R1 image programmed and read back to its exact SHA, exact YWD-1278 GET_VERSION identity verified, exact 128 KiB protected stock image restored and read back to its qualified SHA, and exact stock identity verified; qualification-only write gate closed again and normal product `flash_enabled` remains false
- [x] port AX.25 codec/FCS/parser (0B-P4) — frozen YWD-MMDVM source port; canonical CRC-16/X-25 vector, UI construction, common modulo-8 I/S/U parsing, and two previously physically captured FCS-valid AX.25 frames pass in CI; host-only, no UART/RF access
- [x] port Bell-202 TX serialization (0B-P5) — frozen HDLC/bit-stuff/NRZI/tone-selector implementation; the exact previously over-air-qualified AX25-5B frame still produces 691 selectors and a locked packed-selector SHA256; host-only, no modem command or RF
- [x] port realtime streaming Bell-202 RX (0B-P6) — frozen one-pass 144-hypothesis decoder; exact three-frame physical AX25R3 replay at 1.00x on the target Pi passed with 52.5% processing duty, 47.5% headroom, zero late chunks, negligible drain, no UART access, and no RF
- [ ] port modem protocol/UART owner
- [ ] port TCP KISS framing/server
- [ ] productize bidirectional bounded RX/TX runtime
- [ ] requalify physical RX
- [ ] requalify KISS-originated external-decode TX
- [ ] freeze first product packet-engine checkpoint

## 0C — Channel access / persistent bidirectional TNC

- [ ] deterministic CSMA state-machine tests
- [ ] channel-busy/recent-RX detection
- [ ] TXDELAY
- [ ] PERSIST
- [ ] SLOTTIME
- [ ] bounded TX queues/timeouts/drop accounting
- [ ] KISS parameter commands where applicable
- [ ] persistent RX/TX service qualification

## 0D — Monitor and logging

- [ ] decoded monitor stream
- [ ] MCOM/MCON/MRPT-style controls
- [ ] SQLite frame log
- [ ] MHEARD database/list
- [ ] retention controls
- [ ] diagnostics/status counters

## 0E — Classic TNC console

- [ ] local command shell
- [ ] Telnet command console
- [ ] virtual PTY/serial personality
- [ ] familiar TNC2/MFJ-style command vocabulary
- [ ] STATUS / VERSION / HEALTH modern commands
- [ ] authentication/bind-address hardening for network console

## 0F — UNPROTO / converse / beaconing

- [ ] UNPROTO destination/path
- [ ] CONVERSE mode
- [ ] BTEXT / beacon scheduler
- [ ] jitter and channel-access integration
- [ ] no-beacon-until-CSMA safety gate

## 0G — Native connected-mode AX.25

- [ ] modulo-8 link state machine
- [ ] SABM/UA/DISC/DM
- [ ] I frames and V(S)/V(R)/V(A)
- [ ] RR/RNR/REJ handling
- [ ] T1/T2/T3 timers
- [ ] retry/MAXFRAME/PACLEN controls
- [ ] connected terminal sessions
- [ ] multi-session policy

## 0H — Packet node / mailbox

- [ ] node command layer
- [ ] mailbox/message storage
- [ ] forwarding policy design
- [ ] sysop controls

## Later product work

- WebUI/API
- GitHub update channels and protected rollback
- backup/restore UI
- additional physically-qualified MMDVM HAT targets
- flashable Raspberry Pi image
- first stable release
