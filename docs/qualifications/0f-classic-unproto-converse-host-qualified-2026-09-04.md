# 0F classic UNPROTO/converse host qualification — 2026-09-04

Base appliance checkpoint:

`checkpoint/product-fresh-install-appliance-qualified` @ `e9fc1c4e3810bb7ed63ffd3417d2f3958cd9d1ca`

Development issue/branch:

- issue #36
- `dev-0f-classic-tx`

Host-qualified implementation head:

`ef2f630844e12f7d5ff68e25695a95b0fb84fce0`

Successful implementation CI:

`33938085041`

## Qualified scope

### P1 — UNPROTO

- New `ClassicTXCommandShell` subclasses the frozen 0E-P5 shell; P5 itself remains byte-frozen.
- `UNPROTO` owns per-session destination/path state.
- Direct and bounded `VIA` paths are supported, with at most eight digipeaters.
- AX.25 UI frame bodies are built through the frozen Stage-A codec with no FCS at this layer.
- Invalid destination/path input fails closed without replacing the last valid UNPROTO state.

### P2 — CONVERSE

- `CONVERSE` requires an UNPROTO destination and explicit product TX capability.
- With `radio.tx_enabled=false`, converse refuses before the submit callback can be invoked.
- Converse is line-oriented; one accepted text line invokes the submit callback at most once.
- Text is printable ASCII and bounded by configured `PACLEN`.
- The exact command word `COMMAND` returns the session to command mode.
- There is no automatic/background retry loop in the console layer.
- `BEACON`, `BTEXT`, and `ID` remain deferred to later 0F work.
- Connected-mode commands remain owned by 0G.

### P3 — product composition

- A configured `[station]` selects the 0F console personality; historical host fixtures without `[station]` retain exact frozen P5 behavior.
- Console frame bodies are submitted to the existing live `ProductTNCBackend.reject_client_message(KISS DATA)` boundary.
- 0F creates no second admission queue, CSMA engine, half-duplex implementation, modem owner, UART path, firmware path, or GPIO path.
- Full-daemon qualification deliberately disabled the TCP KISS listener and still proved one console line traversed the existing product admission/CSMA/half-duplex/fake-HAT graph once.
- The fake HAT recorded one TX acceptance, the qualified half-duplex lifecycle restarted RX, and a post-return hold observed no second dispatch.
- TX-disabled full-daemon mode recorded zero fake-HAT TX accepts and no RX stop caused by converse.

## Preservation

The host CI replayed and passed:

- frozen 0E-P5 vocabulary;
- Stage-D classic console graph;
- Stage-B product RX/TX graph;
- Stage-I physical TX evidence contract;
- final fresh-install appliance qualification seal;
- sustained P7/P8 packet lineage.

## Physical boundary

No target Pi was modified, no modem UART was opened, no firmware was written, and no RF was transmitted by 0F host qualification.

**This host qualification does not authorize physical 0F TX.** A separate explicit operator authorization is required before any target-Pi installation/staging or RF test. Beaconing remains out of scope until the UNPROTO/converse physical gate is frozen.
