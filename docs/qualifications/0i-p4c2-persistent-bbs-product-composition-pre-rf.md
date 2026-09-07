# 0I-P4c2 persistent BBS product composition — pre-RF staging

Date: 2026-09-07 UTC

Integration base: `dev` at `b92d1b2dd8195003f901f6df2142946cc2ca7085`.

Frozen mailbox service lineage remains rooted in
`checkpoint/0i-p4b-persistent-bbs-product-service-host-qualified` at
`8103bf095ebd1bd96c0f65800382718557890340`.

Feature branch: `dev-0i-p4c2-mailbox-product-composition`.

## Purpose

P4c2 closes the host-side composition gap between the frozen 0I persistent BBS
and the normal product daemon. It also adds the MFJ-style local `MBOX` terminal
personality. This stage does **not** authorize a target-Pi, modem-UART, HAT, or
RF test.

## Exact host composition under test

Normal daemon composition is required to remain:

1. one `ProductPacketEngine`;
2. one existing `ProductTNCBackend` owned by that engine;
3. `ProductPersistentBBSService` subscribing through that backend's existing
   bounded `open_stream()` PacketEvent interface;
4. connected-BBS responses re-entering that same backend through port-0 KISS
   DATA admission;
5. the existing bounded KISS DATA queue/channel-access implementation deciding
   whether an admitted response may reach the existing downstream TX path;
6. local `MBOX` using the exact `PersistentMailboxStore` opened by the BBS
   service and the frozen `ClassicBBSSession` command personality.

The real-backend host test constructs the actual `ProductTNCBackend`, actual
`ThreadSafeKISSDataAdmissionQueue`, actual immutable TNC parameter state, actual
persistent BBS service/runtime, and actual persistent SQLite mailbox. Only the
final contextual hardware/RF submitter is replaced by an inert recording edge.
Explicit deterministic RSSI observations are required before an admitted BBS
response can reach that fake final edge.

## Required host proofs

- local `MBOX` enters from `cmd:` and returns with `/CMD`, `COMMAND`, raw Ctrl-C,
  or `BYE` without closing the Telnet/PTTY session;
- local mailbox SP/LN/R operations use the shared persistent store and perform
  zero packet submissions;
- a live direct SABM published by the real `ProductTNCBackend` reaches the
  persistent BBS subscriber;
- UA and the first BBS banner I-frame return through the real product DATA
  admission queue;
- no downstream call occurs merely because the BBS service admitted a frame;
- explicit qualified channel observations are required to dispatch queued
  frames, and each request dispatches once;
- `product_tx_enabled=false` rejects port-0 DATA before it enters the queue;
- BBS construction itself refuses connected service when persistent product TX
  authority is disabled;
- service stop unregisters its backend subscription and preserves the mailbox
  database;
- frozen P4b/P4a/P3/P2/P1 behavior remains green;
- current product terminal regressions and package framework self-test remain
  green.

## Preserved safety boundary

P4c2 adds no second modem owner, Bell-202 decoder, UART reader, CSMA engine,
DATA queue, scheduler, transmit retry, firmware writer, GPIO path, or RF path.
The BBS worker may prepare connected-mode protocol actions, but it can only
submit those actions to the already-qualified product KISS DATA admission
boundary. Admission failure remains terminal for the BBS service; P4c2 adds no
application-level retransmission policy beyond the frozen connected AX.25 link
semantics already qualified in 0G/0I-P4a.

The host qualification must leave these markers true:

- `MODEM_UART_OPENED=NO`
- `RF_TRANSMITTED=NO`
- `FIRMWARE_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

## Stop point

After exact-tip CI and a frozen P4c2 host-qualified checkpoint exist, the next
stage may define a bounded physical BBS qualification on 145.050 MHz. No
physical command is intentionally provided by this document.
