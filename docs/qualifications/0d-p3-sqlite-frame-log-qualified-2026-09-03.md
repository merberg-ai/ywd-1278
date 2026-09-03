# 0D-P3 SQLite frame log — host-qualified

Date: 2026-09-03

0D-P3 is host-qualified above the frozen 0D-P2 checkpoint
`checkpoint/0d-p2-monitor-controls-host-qualified` at
`d34db7292750b67384667d99eef897b9306d0113`.

Qualified implementation head:
`3cfb55bb504025c8b00263d5b646a71d14f2ea45`.

## Qualified behavior

The frame logger consumes the existing bounded `RXOnlyBackend` subscriber
queue through the frozen 0D-P1 `MonitorSubscription` decoder.  It adds exactly
one SQLite writer thread and **no additional in-memory queue**.  Slow or failed
storage therefore remains isolated from the packet engine and cannot create an
unbounded RAM backlog.

SQLite schema version 1 uses WAL journal mode and NORMAL synchronous mode.  A
row preserves exact AX.25 frame bytes without FCS, exact information bytes,
source/destination/path, frame class/type, P/F, N(S), N(R), PID, observation
time, monitor-local sequence, and deterministic 0D-P1 rendering.

Logger restart does not replay the backend's in-memory history into SQLite.
The backend atomically registers the live bounded subscriber while returning a
history snapshot; P3 deliberately discards that snapshot and persists only new
live records.  Tests prove a restart produces one row for `ONE` and then one
row for `TWO`, not a duplicate replay of `ONE`.

Unsupported schema versions, unexpected table layouts, and unversioned
non-empty databases fail closed.  A forced SQLite insert failure increments
sink failure accounting, records the fatal error, detaches the logger
subscriber, and leaves the packet backend usable and non-blocking.

## Safety boundary

P1 monitor stream, P2 monitor policy, AX.25 codec, KISS backend, sustained TNC
runtime, and frozen 0C/P8 sources are hash-locked by the P3 architecture
contract.  P3 has no modem dependency, UART access, RF access, transmit API,
GPIO/reset, flash, or option-byte activity.

## CI evidence

Dedicated implementation push CI run `33819172303` passed.

Draft PR #27 exercised the exact implementation head through 16 repository
workflows with zero failures or pending jobs.  `framework-ci` run
`33819204017` completed successfully on the same SHA.

Machine-readable evidence:
`firmware/qualification/0d-p3-sqlite-frame-log-host.json`.

Qualification contract:
`tests/sqlite_frame_log_qualification_contract_test.py`.

## Supplementary target-Pi evidence

Before P3 promotion, the user independently exercised frozen P1/P2 from a
detached worktree on the target Raspberry Pi under Python 3.13.5 while leaving
the deployed 0C/P8 checkout at `fc70386a3857e69437641d1be6f9f8cd0a6e7a13`.
P1, P2, and the frozen P8 preservation regressions all passed with no POSIX
serial transport, UART open, or RF transmission.  That result is preserved
separately in
`firmware/qualification/0d-p1-p2-target-pi-sanity-2026-09-03.json`; it is
supplementary evidence and does not rewrite the original P1/P2 qualification.

A target-Pi P3 SQLite sanity run remains the next external test.  It is
host-only and must not touch the working RF deployment.
