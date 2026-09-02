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
- [ ] shell/Python scaffold qualification on a clean Raspberry Pi

## 0B — Qualified packet engine port

- [ ] port AX.25 codec/FCS/parser
- [ ] port Bell-202 TX serialization
- [ ] port realtime streaming Bell-202 RX
- [ ] port modem protocol/UART owner
- [ ] port TCP KISS framing/server
- [ ] productize bidirectional bounded RX/TX runtime
- [ ] build deterministic `YWD-1278`-branded HAT firmware
- [ ] establish exact first supported target flash geometry/hash
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
