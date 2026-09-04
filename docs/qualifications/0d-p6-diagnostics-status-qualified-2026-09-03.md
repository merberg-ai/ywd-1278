# 0D-P6 diagnostics/status — host qualification

Date: 2026-09-03

## Result

0D-P6 is host-qualified as a read-only, one-shot diagnostics/status aggregation boundary above frozen 0D-P5.

Base checkpoint:

- branch: `checkpoint/0d-p5-retention-host-qualified`
- SHA: `b330e52bdf5eb902135138e32d91ff6538d5cf3c`

Qualified implementation head:

- `0c83530d2565cff22eef9b61dc05b6fa77890d34`
- `src/ywd1278/monitor/diagnostics.py` Git blob: `0f23c1232b51e2f5fbd1a3d4c179e0c94ce4116a`

P5 supplementary target-Pi retention evidence on Python 3.13.5 is preserved before P6 qualification.

## Qualified boundary

`DiagnosticsStatus.snapshot()` observes existing qualified status surfaces only. It can combine:

- sustained runtime accounting/runtime counters;
- packet backend history/subscriber-drop snapshot;
- KISS parameter state;
- KISS control counters;
- KISS DATA ingress counters;
- bounded TX queue counters;
- KISS connection counters;
- SQLite frame-log snapshot;
- MHEARD summary;
- a read-only P5 retention plan.

The result is an immutable `DiagnosticsSnapshot` with the component maps plus `healthy` and an ordered `problems` tuple.

The qualified health problem markers are:

- `runtime-failure`
- `subscriber-drops`
- `tx-access-timeouts`
- `tx-downstream-failures`
- `sqlite-write-failures`
- `sqlite-fatal-error`

A stopped or partially assembled host graph is not automatically classified as unhealthy; absent sources remain absent rather than being guessed. P6 reports known failures/counter conditions only.

## Safety / scheduling boundary

P6 adds no active sampling path. In particular it has:

- no sampling or worker thread;
- no packet subscriber;
- no additional in-memory queue;
- no scheduler or timer loop;
- no direct SQLite connection or database mutation;
- no retention `apply()` capability;
- no automatic VACUUM/checkpoint behavior;
- no modem dependency;
- no UART access;
- no RF access;
- no TX capability.

MHEARD and retention state are queried on demand through their already-qualified P4/P5 read-only interfaces. This keeps diagnostics out of RX/TX scheduling and makes it suitable as the data model for later 0E `STATUS` / `HEALTH` console commands.

## CI

Dedicated P6 workflow:

- workflow: `0d-p6-diagnostics-ci`
- run: `33825023698`
- result: success

The exact implementation head had 14 workflows and finished 14/14 successful. One P3 preservation workflow initially hit the frozen continuous-producer timing regression at its wall-clock edge. The identical frozen P8 regression passed in the dedicated P6 workflow on the same SHA; rerunning only the failed P3 job succeeded as attempt 2. No frozen P8 source or test was changed to clear the timing event.

## Qualification anchors

- `tests/diagnostics_status_test.py`
- `tests/diagnostics_status_contract_test.py`
- `tests/diagnostics_status_qualification_contract_test.py`
- `firmware/qualification/0d-p6-diagnostics-status-host.json`
- `firmware/qualification/0d-p5-retention-target-pi-sanity-2026-09-03.json`

No UART or RF activity occurred during host qualification.
