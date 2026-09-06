# 0I — Persistent classic packet BBS / mailbox

0I turns the physically-qualified 0H node/mailbox building blocks into a durable
old-school packet BBS service.  The frozen 0H prototype mailbox remains intact;
0I uses a dedicated persistent mailbox database and only wires it into the
product after each boundary has been separately host-qualified.

The goal is a familiar packet-radio mailbox rather than a byte-for-byte clone of
LinBPQ.  Commands and presentation should feel conventional to TNC/BBS users,
while storage, ownership, bounds, and runtime behavior remain explicit and
fail-closed.

## Product shape

The completed 0I service is intended to provide:

- persistent personal mail addressed by base callsign, shared across SSIDs;
- bulletins with per-user new/read state;
- bounded subject/body sizes and quotas;
- familiar message numbers and new/read indicators;
- owner-safe message kill with soft-delete semantics;
- optional BID storage/duplicate rejection for future interoperability;
- classic commands including `H/?`, `L`, `LN`, `LR`, `LM`, `R <n>`, `K <n>`,
  `SP <call>`, `SB <topic>`, `INFO/I`, and `B/BYE`;
- persistent operation across service restart;
- one deliberately bounded connected mailbox session at first, reusing the
  already-qualified AX.25 and product TX/channel-access graph;
- later bounded multi-session expansion only after the single-session service is
  physically qualified;
- forwarding remaining disabled unless and until deferred 0H-P12 is physically
  qualified.

## Database separation

0I uses a dedicated mailbox file rather than overloading the existing
`[storage].database`, which is already the qualified monitor/frame-log database.
This avoids mixing two independently-qualified schemas and makes backup,
retention, and later mailbox migrations explicit.

The initial persistent mailbox schema stores:

- message type: personal (`P`) or bulletin (`B`);
- base-callsign sender;
- personal recipient or bulletin topic;
- subject and body;
- creation timestamp;
- optional unique BID;
- soft-kill timestamp;
- per-user read receipts.

The mailbox identity is the base callsign, so `KJ6YWD-1`, `KJ6YWD-10`, and
`KJ6YWD-15` share the `KJ6YWD` mailbox.  AX.25 link identity and authorization
remain exact-address concerns outside the store.

## Stages

### 0I-P1 — persistent mailbox core, host-only

- dedicated mode-0600/inode-protected SQLite store;
- personal mail and bulletins;
- base-callsign mailbox identity across SSIDs;
- independent per-user new/read state;
- owner-safe soft kill;
- optional normalized unique BID;
- bounded quotas and list sizes;
- reopen/restart persistence tests;
- no daemon/runtime/modem/KISS/link/RF integration.

### 0I-P2 — classic BBS command personality, host-only

Build a bounded session adapter over the frozen P1 store with familiar commands:

- `H` / `?` — help;
- `L` — current visible messages;
- `LN` — new/unread messages;
- `LR` — visible messages oldest first;
- `LM` — messages sent by the connected user;
- `R <n>` — read a visible message and mark it read;
- `K <n>` — owner-authorized kill;
- `SP <call>` — send personal mail;
- `SB <topic>` — send bulletin;
- `I` / `INFO` — BBS information;
- `B` / `BYE` — orderly session exit.

Composition remains bounded and ends with `/EX`; `/ABORT` cancels without a
partial deposit.  P2 does not own a link or transmit.

### 0I-P3 — persistent node/mailbox product configuration, host-only

Introduce explicit safe product configuration, expected to include a dedicated
`[node]` / `[mailbox]` boundary.  Mailbox storage must use an absolute dedicated
path and remain disabled unless the node service is explicitly enabled.  The
normal example configuration remains safe/no-TX.

### 0I-P4 — persistent connected mailbox runtime, host-only

Compose the already-qualified connected-mode link/session machinery, inbound
node/BBS personality, persistent mailbox store, and existing product TX
admission boundary under fake/injected transports.  Initially permit exactly
one connected mailbox link owner.  Prove restart/teardown behavior, queue bounds,
no duplicate responses, and no second RF/TX path.

### 0I-P5 — guarded physical persistent service qualification

On 145.050 MHz, exercise the installed systemd service with a real remote packet
station.  The acceptance run should connect, display the BBS banner/help, list,
send personal mail, send/read a bulletin, mark read state, kill an owned message,
disconnect, restart the service, reconnect, and prove surviving mailbox state.
The normal safe service state must be restored afterward.

### 0I-P6 — sysop mailbox maintenance, host then physical as needed

Add bounded local/sysop controls for mailbox stats, quotas, killed-message purge,
and backup-safe maintenance.  No shell escape and no implicit forwarding.

### 0I-P7 — classic BBS sustained-session qualification

Exercise repeated users/sessions, command fragmentation, large-but-bounded
messages, reconnects, service restart, mailbox quota boundaries, read-state
isolation, and failure recovery.  Only after P7 should the persistent packet BBS
be treated as the full service mailbox product boundary.

## Forwarding boundary

0I does not activate automatic forwarding.  The host-qualified 0H-P11 plumbing
remains present but `forwarding.enabled=false` is the product gate.  Physical
BBS-to-BBS forwarding remains deferred to 0H-P12 until a forwarding-capable peer
or dedicated test system is available.
