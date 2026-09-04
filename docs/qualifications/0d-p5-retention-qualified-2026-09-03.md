# 0D-P5 bounded retention controls — host qualified

Date: 2026-09-03

## Frozen base

0D-P5 is built above the frozen 0D-P4 checkpoint:

- `checkpoint/0d-p4-mheard-host-qualified`
- `d75e253003762d1077e7300da52980b1f4739963`

The qualified P4 MHEARD implementation and P3 SQLite logger remain byte-for-byte frozen. The successful P4 target-Pi sanity run on Python 3.13.5 is preserved separately in `firmware/qualification/0d-p4-target-pi-sanity-2026-09-03.json`.

## Qualified retention boundary

`src/ywd1278/monitor/retention.py` adds explicit SQLite maintenance only.

Retention is disabled by default. A typed policy may optionally set:

- maximum frame age (`max_age_ns`),
- maximum retained row count (`max_rows`), or
- both, with a row eligible when either limit requires removal.

Planning is read-only. Deletion occurs only when the caller explicitly invokes `apply()`.

Each apply operation:

1. validates the exact P3 schema version and required `frames` columns,
2. acquires one `BEGIN IMMEDIATE` transaction,
3. selects the oldest eligible rows deterministically,
4. deletes at most 1000 rows by default,
5. never permits a configured batch above 10000 rows,
6. commits once and reports whether further eligible rows remain.

A competing SQLite writer causes a bounded failure (`RetentionBusyError`). P5 does not loop, retry, sleep, schedule itself, or wait indefinitely for the database.

P5 performs no automatic `VACUUM` and no automatic WAL checkpoint. It makes no schema change. The frozen P4 MHEARD view automatically reflects whatever rows remain in the qualified P3 `frames` table.

## Safety boundary

P5 adds:

- no packet-event subscriber,
- no worker thread,
- no additional in-memory queue,
- no modem dependency,
- no UART access,
- no RF access,
- no TX capability,
- no GPIO/reset/flash/option-byte path.

The retention controller has no `start`, `stop`, `open_stream`, `publish`, `transmit`, `send`, or `submit` operation.

## Qualification

Qualified implementation head:

`61cd2ff68ad7b4be22185c7f50bdab6da8418c11`

Retention implementation blob:

`1e08367d98f39e15eaeb855ef5e6e6b39eef9302`

Dedicated push qualification:

- workflow: `0d-p5-retention-ci`
- run: `33823733130`
- result: success

Pull request qualification:

- PR: #29
- full matrix: 18/18 successful
- framework run: `33823771799` — success
- P5 run: `33823771856` — success
- failed/pending: 0/0

The regression suite covers disabled-default behavior, age retention, row-count retention, combined policy semantics, bounded batches, busy-writer failure, schema rejection, MHEARD after pruning, invalid controls, and absence of packet/TX surfaces.

Machine-readable evidence is stored in `firmware/qualification/0d-p5-retention-host.json` and enforced by `tests/retention_qualification_contract_test.py`.
