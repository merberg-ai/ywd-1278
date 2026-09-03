# 0D-P2 MCOM/MCON/MRPT monitor policy — host qualified

0D-P2 is host-qualified above the frozen 0D-P1 decoded monitor stream.

## Frozen base

- checkpoint: `checkpoint/0d-p1-decoded-monitor-host-qualified`
- base SHA: `1972f4c92552085202c810e3b605c8e46275634c`
- qualified implementation head: `b42842b36ff29dee146a2c74ede1e98bb7d144ba`
- P2 policy blob: `f7d105554f682dfc533a09bff8823b192e5debe9`
- frozen P1 monitor blob: `703b7e803d39d915b60d79c30c154151e3820098`

## Qualified controls

The typed policy defaults are `MCOM OFF`, `MCON OFF`, `MRPT ON`.

- MCOM OFF suppresses AX.25 S frames and non-UI U protocol/control frames from the monitor view. I and UI information records remain eligible. MCOM ON exposes those protocol/control records.
- MCON OFF matters only when an explicit future-link-layer context says a local connected-mode session exists. In that context, third-party eligible monitor records are suppressed while records explicitly identified as addressed to the local station remain eligible. MCON ON permits all otherwise-eligible records. No connected-mode engine is introduced in 0D.
- MRPT ON renders the complete decoded path including repeated `*` state. MRPT OFF removes the path only from presentation; immutable `MonitorRecord.path` is not changed.

Policy updates are thread-safe, atomic and generation-tagged. One effective multi-field update increments generation exactly once; an idempotent update does not.

0D-P2 intentionally exposes typed state only. Text command parsing and local/Telnet command consoles remain 0E work.

## CI evidence

Dedicated P2 push CI run `33815606268` passed on the exact implementation head. PR #26 triggered 15 repository pull-request workflows on the same SHA, including framework-ci run `33815650153`; all completed successfully with zero pending and zero failed runs.

Two earlier staging runs failed only test/contract fixtures: the first supplied `path=None` to the frozen AX.25 builder; the second matched a forbidden network token in policy documentation text. Neither failure changed the frozen P1 or 0C implementation boundary.

## Safety boundary

P2 has no modem or TX imports, no command/network listener, no UART/RF operation, and no GPIO/reset, flash, or option-byte activity. The P1 monitor stream and frozen 0C source blobs remain protected by contracts.
