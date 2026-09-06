# 0I-P1 persistent mailbox core — host qualified

Date: 2026-09-06 UTC

Base checkpoint: `checkpoint/0h-p11-forwarding-plumbing-host-qualified`
(`264831a5daabed3a929886230f7412126f0b3e04`)

Candidate head: `ce5da5434b6af558aaece291159bd7d8aaa08c00`

Candidate CI: `34007888098` — PASS

Qualified source blob:

- `src/ywd1278/node/persistent_mailbox.py`
- Git blob `f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc`

## Qualified behavior

P1 establishes the durable storage boundary for the future persistent classic
packet BBS:

- dedicated protected SQLite database rather than the qualified monitor/frame
  log database;
- schema version 1 with exact structural validation;
- mode `0600`, regular-file requirement, symlink refusal, and inode identity
  checks around every connection;
- personal (`P`) messages and bulletin (`B`) messages;
- base-callsign mailbox ownership shared across AX.25 SSIDs;
- independent per-user new/read receipts, including bulletins;
- owner-safe soft kill: personal recipient or original sender; bulletins only by
  original sender;
- optional upper-normalized unique BID with duplicate rejection;
- 64-byte printable-ASCII subjects and 4096-byte printable-ASCII/CR/LF bodies;
- bounded list views and bounded total/per-user/bulletin quotas;
- sent-message view and mailbox counts;
- state survives store close/reopen;
- foreign users cannot read personal mail addressed to another callsign.

## Preserved boundaries

The frozen 0H prototype mailbox and P11 forwarding plumbing remain byte-exact.
P1 is not imported by the daemon or appliance layers and has no modem, KISS,
connected-link, UART, TX, RF, scheduler, forwarding-dispatch, flash, GPIO/reset,
or option-byte ownership.

No target-Pi or RF test is required for P1.  The first persistent service RF
qualification is intentionally deferred to later 0I stages after command,
configuration, and runtime composition are host-qualified.
