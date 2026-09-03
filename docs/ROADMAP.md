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
- [x] 0B-P10 deterministic packet-capable YWD-1278 AX25R3 firmware build from frozen engineering source — exact `d25180ad663d781b761c525d1e699e7b052d6214` lineage, product branding made no behavioral changes after AX25R3, two independent builds were byte-identical, artifact size `59812`, SHA256 `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`; the twelve exact engineering blobs are now vendored and Git-blob-verified inside YWD-1278 so reproducing the build no longer requires a YWD-MMDVM checkout
- [x] 0B-P11 guarded packet-firmware write/readback/runtime-identity/exact-stock-restore round trip — exact P10 artifact programmed/read back to SHA `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`, exact product AX25R3 GET_VERSION identity verified, exact protected 128 KiB stock image restored/read back to SHA `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`, final exact stock identity verified; GET_VERSION only, no RX start/TX/RF, P11 gate closed again
- [x] 0B-P12a guarded packet activation + physical live RX owner/FIFO lifecycle — receive path physically qualified with zero FIFO drops and zero TX activity; exact packet firmware intentionally remains installed for P12b
- [x] 0B-P12b live over-air packet -> YWD_RX -> streaming Bell-202 -> AX.25 event -> TCP KISS qualification — physically qualified RX-only at 145.050 MHz with one live `KJ6YWD>JIM` UI frame delivered through TCP KISS; 27101 packed bytes, 2511 YWD_RX reads, 24 status checks, 216815 firmware samples, zero FIFO drops, zero KISS subscriber drops, inbound KISS DATA rejected exactly once, RF keyups `0->0`, RF TX generated samples `0->0`, UART released, no flash/GPIO/TX/option-byte activity
- [x] 0B-P13a bounded TX broker host qualification — added a narrow `TXModemOwner` subclass with one typed selector-burst operation while preserving the frozen RX-only `ModemOwner`; bounded broker defaults TX-disabled, requires valid AX.25 FCS, reuses the exact P5 45/3-flag serializer, caps bursts at 1920 selectors, preflights modem pending selectors, fails closed on full queue, reproduces the frozen 691-selector/87-byte reference burst SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`, and leaves KISS/daemon TX completely disconnected; host-only, no UART or RF transmission
- [x] 0B-P13b guarded known-packet YWD TX on 145.050 MHz with independent external decoder/receiver proof — **physically qualified by P13b-R2** at RF power `200/255`. Exactly three fixed `KJ6YWD-10>YWD13B` R2 verification packets were submitted through the bounded P13a broker, each 745 selectors / 11920 generated samples with one completed keyup under reset-on-accept diagnostics and fixed 5.0 s gaps. The independent 1200-baud receiver decoded all three exact frames (`R2 VERIFY 1/3`, `2/3`, `3/3`). UART released cleanly; no flash, GPIO/reset, option-byte writes, automatic retry, ordinary KISS TX, or persistent product TX occurred. Original one-shot and R1 partial-attempt evidence remain frozen historically
- [ ] connect KISS-originated TX only through the bounded broker and subsequent CSMA/channel-access policy
- [ ] requalify KISS-originated external-decode TX
- [ ] freeze first product packet-engine checkpoint

## 0C — Channel access / persistent bidirectional TNC

- [x] deterministic CSMA state-machine tests (0C-P1) — host-qualified p-persistent policy with frozen `PERSIST=63` (25%), `SLOTTIME=10` (100 ms), 30 s bounded wait, explicit caller-supplied time/randomness, no assumed initial channel state, explicit clear required before a full slot begins, busy observations cancel/reset clear-slot timing, exhaustive PERSIST boundary tests, sticky terminal states, and no modem/KISS/RF integration
- [x] channel-busy/recent-RX detection (0C-P2) — exact AX25R4 firmware SHA256 `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616` is physically installed and qualified as a read-only raw-RSSI source. Two distinct FCS-valid `KJ6YWD>JIM` packets on 145.050 MHz correlated at packet-window median raw RSSI `48`; an independent 243-sample outside-frame population had median `106`, proving lower raw = stronger RF with a `58`-count margin. Physical signal/transition values ended at `70`, the upper population began at `97`, leaving a 27-count empty guard region. A host-only fail-closed detector is qualified with busy assert `<=83`, clear release `>=90`, hysteresis `84..89`, and 250 ms continuous-clear/recent-RX hold. Startup is non-clear; only CLEAR is eligible for later CSMA use. This P2 boundary remains frozen; its first live integration is separately qualified by P3
- [x] live RSSI -> 0C-P2 detector -> unchanged 0C-P1 CSMA shadow integration (0C-P3) — physically qualified on the already-installed AX25R4 firmware at 145.050 MHz. One FCS-valid `KJ6YWD>JIM` UI frame was decoded while raw RSSI `48` drove detector BUSY and forced P1 back to `WAIT_CLEAR` after 26 intentional pre-busy persistence deferrals. RECENT_RX remained busy-for-access; detector CLEAR at 4.701 s started a fresh full slot; explicit byte `255` deferred at 4.850 s (149 ms later); explicit byte `0` reached shadow READY at 4.955 s (105 ms later). 100 RSSI samples, 11965 packed bytes, zero FIFO drops, RF keyups `0->0`, generated TX samples `0->0`, one modem owner, no TX broker, no KISS/product TX, no flash/GPIO/option-byte activity
- [x] bounded queued TX request -> qualified P3 channel access -> injected fake submitter (0C-P4a) — host-qualified with default capacity 4, valid FCS required before queue admission, a 30 s total lifetime measured from enqueue so queue waiting consumes the same deadline, a fresh P3 attempt per head request, one RSSI observation advancing only one request, READY dispatch exactly once, and downstream failure terminal with no automatic retry. CI uses fake submitters only; concrete `TXBroker`, `TXModemOwner`, KISS/product TX, UART, and RF remain disconnected
- [x] compose P4a with the concrete qualified `TXBroker` over a fake modem port (0C-P4b) — host-qualified direct composition with no glue layer. The real broker preserves its frozen P5 38-byte / 691-selector / 87-packed-byte serializer anchor SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`; modem-busy, broker-disabled, selector-overflow, and downstream errors all remain terminal/no-retry P4a outcomes. `TXModemOwner`, modem transport, UART, KISS/product TX, and RF remain absent
- [x] compose P4a + real `TXBroker` + real single-owner `TXModemOwner` over a fake thread-bound transport (0C-P4c) — host-qualified full software graph. Zero modem transactions occur before CSMA READY; afterward exactly `YWD_RF/GET_STATUS` then `YWD_RF/TX_TONES` are emitted on the single owner thread, carrying the same frozen 691-selector P5 burst; transport close also occurs on that owner thread and later RSSI observations cannot duplicate dispatch. POSIX serial, UART, hardware, KISS/product TX, and RF remain disconnected
- [x] guarded physical channel-access-controlled TX through the real POSIX modem transport (0C-P4d) — **physically qualified by P4d-R2** at 145.050 MHz / RF power `200/255`. Active AX25R4 RX polled RSSI while draining `28942` packed bytes with zero FIFO drops; 81 forced-255 pre-busy persistence trials could not transmit. A real raw-RSSI `48` BUSY at 10.700 s forced `WAIT_CLEAR`; CLEAR at 11.800 s was followed by a full 100 ms slot and `255` defer at 11.900 s, then another full slot and `0` READY at 12.050 s. R2 performed the firmware-required half-duplex `RX_STOP` handoff before the real broker, submitted exactly one fixed 46-byte / 753-selector frame, and an independent receiver decoded the exact `KJ6YWD-10>YWD4D:YWD-1278 P4D CSMA VERIFY 1/1` packet. No duplicate dispatch, automatic retry, KISS/product TX, flash, GPIO/reset, or option-byte activity occurred. R1's pre-TX missing-`RX_START` NAK remains frozen as historical evidence
- [ ] persistent half-duplex RX -> channel access -> RX_STOP -> TX -> RX restart scheduler qualification, still with KISS-originated TX disconnected
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
