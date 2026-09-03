# 0C-P7 live KISS one-shot — staged

Date: 2026-09-03

## Purpose

This is the guarded physical follow-on to the host-qualified 0C-P7 KISS DATA
admission boundary.  It authorizes exactly one fixed localhost KISS DATA message
to traverse the real P7 graph and, only after qualified live channel access,
produce one RF burst on the already-qualified AX25R4 hardware.

Base checkpoint:

`checkpoint/0c-p7-kiss-data-admission-host-qualified`

Base SHA:

`3df9a46f0851876e55c078ab41504584304bef38`

## Fixed RF profile

- device: `/dev/ttyAMA0`
- frequency: 145.050 MHz
- RF power: 200/255
- installed firmware: existing physically-qualified AX25R4; no reflash
- source: `KJ6YWD-10`
- destination: `YWD7`
- AX.25 path: literal `VIA YWDNOD`
- information: `YWD-1278 P7 KISS VERIFY 1/1`
- YWDNOD repeated/H-bit proof: deferred and non-blocking

Expected direct decode:

`KJ6YWD-10>YWD7,YWDNOD:YWD-1278 P7 KISS VERIFY 1/1`

## KISS-originated vector

The localhost KISS client sends the AX.25 body without FCS.  The host-qualified
P7 admission path validates the body and appends the AX.25 FCS exactly once.

- KISS body: 50 bytes
- KISS body SHA256: `ab21f1684442a24693a4a8f35b0ef5febaa007703d67609005c31e99332ecef3`
- FCS-bearing frame: 52 bytes
- FCS-bearing frame SHA256: `a5aeebc7fb9dadeab9264a5deed8973b7b41a8acbdb2932a78e40dde814d2985`
- TXDELAY: 30 / 300 ms / 45 opening flags
- PERSIST: 63
- SLOTTIME: 10 / 100 ms
- parameter generation after the three real KISS parameter commands: 3
- selectors: 801
- packed selector bytes: 101
- packed selector SHA256: `82fff4f7b03ae787fb16d6d14cc9a59e81e7b3f751a3e4be1e090320d26b2b7f`
- generated samples: 12816

## One-shot ingress gate

The harness starts a KISS server only on `127.0.0.1` with an ephemeral port,
sends exactly three parameter commands plus one fixed DATA message through a
real TCP socket, verifies one DATA admission, and closes the KISS listener
before channel-access scheduling is allowed to dispatch.

There is therefore no persistent KISS TX interface during the RF portion of the
qualification and no opportunity for a second client packet to be admitted.

## Live channel-access gate

Before the queued KISS request can transmit, passive RX must be active and
zero-drop.  A fresh non-P7 FCS-valid AX.25 packet and live BUSY must both be
observed.  Qualification randomness remains deterministic:

- before the fresh decoded BUSY trigger: 255 only;
- first post-trigger persistence trial: 255 defer;
- second post-trigger persistence trial: 0 dispatch.

Each persistence trial must occur only after a complete 100 ms SLOTTIME slot.

## Half-duplex and recovery gate

READY passes through the exact host-qualified P4e lifecycle and contextual P5
TXDELAY path:

`RX_STOP -> one contextual TX -> RF idle -> RX_START`

After that restart, one additional non-P7 FCS-valid inbound packet must decode
while the P7 transmit queue is empty.  A direct echo or `YWDNOD*` repeat of the
qualification packet may be displayed but cannot satisfy this final RX proof.

## Safety invariants

- maximum KISS DATA messages admitted: 1
- maximum transmit submissions: 1
- automatic retry: forbidden
- persistent KISS TX: disabled
- product TX: disabled
- direct/raw modem TX calls from the harness: forbidden
- flash: forbidden
- GPIO/reset: forbidden
- option bytes: forbidden
- independent direct decode of the outgoing packet: required
- if one TX has been accepted and any later check fails, the full harness must
  not be rerun; preserve the output and diagnose that one-shot state instead.

The default harness invocation is a no-hardware dry run and exits before modem
owner construction or KISS listener startup.
