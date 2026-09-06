# 0I-P3 persistent node/mailbox configuration — host qualified

Date: 2026-09-06 UTC

Base checkpoint: `checkpoint/0i-p2-classic-bbs-commands-host-qualified`
(`a6dc04c6caa2eaea9e0c3ac76e6d34e034fce4de`)

Candidate head: `bf10534265891e99b3c0100564d81b83c7b9d66e`

Candidate CI: `34008269050` — PASS

Qualified source blob:

- `src/ywd1278/service/node_mailbox_config.py`
- Git blob `a56d8981888ebffd1aa22d895d53db7326e9d6bc`

## Qualified behavior

- missing `[node]` and `[mailbox]` tables preserve safe disabled defaults;
- example configuration explicitly contains disabled node/mailbox sections;
- enabled service resolves the exact `[station]` AX.25 identity;
- node alias is bounded to 1..6 alphanumeric ASCII characters;
- `node.max_sessions` is pinned to one until later sustained-session qualification;
- node and mailbox activation must be paired;
- mailbox database path must be absolute and must not equal the qualified monitor/frame-log `[storage].database`;
- default persistent mailbox path is `/var/lib/ywd-1278/mailbox.sqlite3`;
- mailbox PACLEN is bounded to 32..256 with default 128;
- mailbox information text is bounded printable ASCII.

## Preserved boundaries

The frozen P1 persistent store and P2 classic BBS personality remain byte-exact.
P3 owns no runtime capability and is not yet imported by the daemon.  There is
no connected-link owner, database creation at daemon startup, modem/UART, KISS,
TX, RF, scheduler, forwarding activation, flash, GPIO/reset, or option-byte
activity.

No target-Pi or RF test is required for P3. Runtime composition begins at 0I-P4.
