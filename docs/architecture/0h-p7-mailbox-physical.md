# 0H-P7 guarded mailbox physical acceptance

0H-P7 stages one exact live mailbox round trip over the physically qualified inbound link. The remote is fixed to LinBPQ's outgoing `KJ6YWD-15` identity, while its listener remains `KJ6YWD-5`.

The operator must run HELP, an empty LIST, `SP KJ6YWD-15 P7 TEST`, the exact body `YWD-1278 0H-P7 MAILBOX TEST 1/1`, `/EX`, a populated LIST, `READ 1`, and BYE. The harness verifies one exact stored record, at least two listings, an owner read, acknowledged BYE, and orderly release.

The mailbox database exists only below `/run/ywd-1278-0h-p7` and is removed on every exit path. The guarded harness requires root, recognized firmware, qualified P6 ancestry, exact CLI and interactive authorization, and the byte-stable persistent no-TX appliance. It restores normal service and never flashes firmware or writes option bytes.
