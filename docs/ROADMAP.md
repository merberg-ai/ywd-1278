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
- [x] port modem wire protocol codec (0B-P7a) — preserves qualified `YWD_CONTROL`, `YWD_RF`, and RX3 `YWD_RX` opcodes/layouts; malformed frames fail closed; the frozen 691-selector AX25-5B request serializes exactly; pure bytes only, no UART/RF access
- [x] bounded single-owner runtime architecture (0B-P7b-1) — transport created/used/closed in exactly one owner thread; typed receive/control API only; bounded queue fails closed; no raw client transact and no TX owner API; deterministic fake-transport qualification
- [x] thread-bound POSIX serial transport + guarded live read-only owner identity proof (0B-P7b-2) — real `/dev/ttyAMA0`, exactly one owner thread and one `GET_VERSION` transaction, exact stock identity, UART released afterward; no GPIO/RX/TX/RF/flash
- [x] live YWD_RX owner/FIFO qualification (0B-P12a) — exact P10/P11 packet firmware activated from exact stock, exact programmed readback and product identity verified, RX configured at 144.390 MHz, 57662 firmware samples advanced during a 3 s live receive-only run, 7210 packed bytes drained with peak FIFO occupancy 4 bytes and zero drops, active/idle flags `0x0D`/`0x04`, RF keyups and TX generated samples remained `0->0`, exactly one modem owner released the UART, and the packet firmware was left installed after a cold restart; P12a activation gate closed after proof
- [x] port TCP KISS framing/server (0B-P8) — standard port-0 DATA framing and stream resynchronization; real localhost TCP delivery of all three saved physically sourced frames; bounded client queues with zero drops; inbound client DATA explicitly rejected; no UART/RF/TX path
- [x] assemble RX-only product runtime (0B-P9) — single owner -> YWD_RX revision-3 FIFO -> Bell-202 -> AX.25 event bus -> TCP KISS; target-Pi replay consumed all 24,009 packed bytes, decoded/delivered the same three physical frames, rejected inbound KISS DATA, and reported zero FIFO/subscriber drops with no real UART/RF access
- [x] 0B-P10 deterministic packet-capable YWD-1278 AX25R3 firmware build from frozen engineering source — exact `d25180ad663d781b761c525d1e699e7b052d6214` lineage reconstructed from pinned Git objects, product branding made no behavioral changes after AX25R3, two independent builds were byte-identical, artifact size `59812`, SHA256 `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- [x] 0B-P11 guarded packet-firmware write/readback/runtime-identity/exact-stock-restore round trip — exact P10 artifact programmed/read back to SHA `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`, exact product AX25R3 GET_VERSION identity verified, exact protected 128 KiB stock image restored/read back to SHA `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`, final exact stock identity verified; GET_VERSION only, no RX start/TX/RF, P11 gate closed again
- [x] 0B-P12a guarded packet activation + physical live RX owner/FIFO lifecycle — receive path physically qualified with zero FIFO drops and zero TX activity; exact packet firmware intentionally remains installed for P12b
- [x] 0B-P12b live over-air packet -> YWD_RX -> streaming Bell-202 -> AX.25 event -> TCP KISS qualification — physically qualified RX-only at 145.050 MHz with one live `KJ6YWD>JIM` UI frame delivered through TCP KISS; 27101 packed bytes, 2511 YWD_RX reads, 24 status checks, 216815 firmware samples, zero FIFO drops, zero KISS subscriber drops, inbound KISS DATA rejected exactly once, RF keyups `0->0`, RF TX generated samples `0->0`, UART released, no flash/GPIO/TX/option-byte activity
- [x] 0B-P13a bounded TX broker host qualification — added a narrow `TXModemOwner` subclass with one typed selector-burst operation while preserving the frozen RX-only `ModemOwner`; bounded broker defaults TX-disabled, requires valid AX.25 FCS, reuses the exact P5 45/3-flag serializer, caps bursts at 1920 selectors, preflights modem pending selectors, fails closed on full queue, reproduces the frozen 691-selector/87-byte reference burst SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`, and leaves KISS/daemon TX completely disconnected; host-only, no UART or RF transmission
- [ ] 0B-P13b guarded known-packet YWD TX on 145.050 MHz with independent external decoder/receiver proof — first physical one-shot **passed all internal RF evidence** (`1` submission, keyups `0->1`, generated samples `0->12048`, idle after completion, UART released) but external decode was not confirmed. P13b-R1 then submitted burst 1 but hit a host checker false-negative because firmware TX diagnostics reset on every accepted burst; bursts 2/3 were not submitted. P13b-R2 is now staged/CI-gated with corrected per-burst accounting and the previously independently decoded AX25-5B RF level `200/255`: exactly three fixed `R2 VERIFY 1/3`, `2/3`, `3/3` packets, each 745 selectors / 11920 generated samples, fixed 5.0 s gaps, no automatic retry, and ordinary KISS/product TX still disconnected
- [ ] connect KISS-originated TX only through the bounded broker and subsequent CSMA/channel-access policy
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
