# 0D-P4 MHEARD host qualification — 2026-09-03

## Result

0D-P4 is host-qualified above the frozen 0D-P3 checkpoint.

- Base checkpoint: `checkpoint/0d-p3-sqlite-frame-log-host-qualified`
- Base SHA: `0c6778278469ab5f1608cdc9e38d02bc0987541f`
- Qualified implementation head: `b32f070611075634507b089e9dcee86122ac5a58`
- MHEARD source blob: `09a9dd17cee8eff2ef9aa3df418a3e575e1f985e`
- Dedicated P4 push CI: `33820815962` — success
- PR: #28
- Framework PR CI: `33820856458` — success
- Full PR matrix: 17/17 success

## Architecture

`MHeardDatabase` is an on-demand, read-only view over the exact SQLite `frames` table already qualified by 0D-P3.

It does **not** subscribe to the packet event backend. It introduces no packet queue, no worker thread and no duplicate live consumer. The P3 SQLite logger remains byte-for-byte frozen.

SQLite is opened through a `mode=ro` URI and immediately placed in `PRAGMA query_only=ON`. P4 contains no INSERT/UPDATE/DELETE/schema-mutation operation.

## MHEARD semantics

Station identity is the exact AX.25 source callsign plus SSID. `KJ6YWD` and `KJ6YWD-9`, for example, are distinct heard entries.

For each heard source P4 returns:

- exact source string;
- base callsign and SSID;
- first-heard timestamp;
- last-heard timestamp;
- heard frame count;
- latest destination;
- latest digipeater path;
- latest frame class/type;
- latest deterministic monitor line.

Latest-route selection is deterministic: `(observed_at_ns DESC, id DESC)`. An optional `since_ns` window recomputes counts and first/last timestamps inside the requested window. List size is explicitly bounded to 1..1000 entries.

## Qualification coverage

Regression tests prove:

- source callsign+SSID aggregation;
- SSID separation;
- correct first/last heard values;
- deterministic latest destination/path/line selection;
- bounded result limits;
- time-window filtering;
- exact source lookup normalization;
- fail-closed unsupported frame-log schema handling;
- absence of packet/TX operations on the MHEARD surface.

The architecture contract additionally hash-locks the frozen P3/P2/P1 sources and the frozen 0C runtime boundary while rejecting packet-backend imports, worker-thread/queue primitives, SQLite write SQL, modem/TX imports, UART paths and GPIO access.

## Preserved target-Pi evidence

The user's successful P3 target-Pi sanity run is preserved separately in `firmware/qualification/0d-p3-target-pi-sanity-2026-09-03.json`.

That run used Python 3.13.5 at merged checkpoint `0c6778278469ab5f1608cdc9e38d02bc0987541f`, passed the P3 regression/architecture/qualification contracts, preserved P1/P2, and created/read a real two-row WAL SQLite smoke database with no UART or RF activity.

## Safety boundary

0D-P4 adds no:

- PacketEvent subscriber;
- packet/RX queue;
- worker thread;
- SQLite write capability;
- modem dependency;
- UART access;
- RF operation;
- transmit operation;
- GPIO/reset/flash/option-byte operation.

0D-P4 remains host-only. Live RF integration is a later, separately guarded qualification boundary.
