# 0D-P3 — SQLite frame log architecture

0D-P3 persists the already-decoded 0D-P1 monitor record without changing the
qualified RF, modem, Bell-202, AX.25, KISS, CSMA, or TX paths.

## Data path

```text
qualified PacketEvent backend
          |
          v
existing bounded subscriber queue
          |
          v
frozen 0D-P1 MonitorSubscription decoder
          |
          v
one SQLite writer thread
          |
          v
frames.sqlite3
```

The logger deliberately adds **no second in-memory queue**.  `RXOnlyBackend`
remains the authoritative bounded queue and drop-accounting boundary.  A slow
or failed disk therefore cannot block RX/CSMA/TX and cannot create an unbounded
RAM backlog.

## Restart semantics

Opening the backend stream atomically returns a history snapshot and registers
the live bounded queue.  P3 intentionally discards that history snapshot and
constructs the frozen `MonitorSubscription` with an empty history list.  Events
published after registration remain in the live queue.  Restarting the SQLite
logger therefore resumes with new observations and does not duplicate the
backend's in-memory history.

## SQLite ownership

Exactly one dedicated `ywd1278-sqlite-frame-log` thread owns the SQLite
connection.  The database uses schema version 1, WAL journal mode, and NORMAL
synchronous mode.  Existing databases with an unsupported schema version, an
unexpected `frames` layout, or an unversioned non-empty schema are rejected
fail-closed.

Each row stores:

- observation timestamp in nanoseconds;
- monitor-local sequence number;
- source and destination;
- JSON digipeater path including `*` repeated markers;
- AX.25 frame class/type, P/F, N(S), N(R), and PID;
- exact information bytes;
- exact AX.25 frame bytes without FCS;
- deterministic 0D-P1 monitor rendering.

History-replay records are forbidden from persistence at the insertion
boundary.

## Failure isolation

A SQLite insert/commit failure increments logger failure accounting, records a
fatal error, detaches the bounded subscriber, and terminates only the logger
thread.  It does not stop or mutate the packet backend and has no modem, UART,
RF, GPIO/reset, flash, option-byte, or transmit capability.

## Deferred work

0D-P3 is storage only.  MHEARD derivation, retention policy, diagnostics/status
presentation, command parsing, and live appliance/console wiring remain later
0D/0E work.
