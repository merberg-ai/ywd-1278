# 0E-P1 local classic TNC command shell — host qualified

Date: 2026-09-03

## Result

0E-P1 is host-qualified as a bounded local stdin/stdout command shell above the frozen 0D monitor/logging stack.

Base checkpoint:

- branch: `checkpoint/0d-p6-diagnostics-status-target-pi-qualified`
- SHA: `de90a5613c2c3be47f485842920239b7067c249a`

Qualified implementation head:

- `a0d06cb59236d049b9896d80378df5957cc6d3ac`
- `src/ywd1278/console/local.py` Git blob: `9fed5416ca9123811413f4ef284abff0006a48dd`

## Qualified local-console boundary

The package now exposes a dedicated local entry point:

```text
ywd1278-console
```

The console uses normal process stdin/stdout only and presents the familiar local command prompt:

```text
cmd:
```

Input is bounded to 256 command characters. Overlong input is rejected and the remainder of that line is discarded before the next command is parsed. Commands are case-insensitive but exact-token: there is no command abbreviation, shell escape, command substitution, dynamic module loading, `eval`, or `exec` path.

The host-qualified command set is:

- `HELP` / `?`
- `VERSION`
- `STATUS`
- `HEALTH`
- `MHEARD [1-100]`
- `MCOM [ON|OFF]`
- `MCON [ON|OFF]`
- `MRPT [ON|OFF]`
- `QUIT` / `EXIT`

`STATUS` and `HEALTH` consume only a caller-supplied frozen 0D-P6 one-shot diagnostics snapshot. When no diagnostics source is attached they say `UNAVAILABLE` rather than inventing runtime state. `STATUS` also reports how many of the ten qualified component surfaces are present.

`MHEARD` binds only to the frozen 0D-P4 read-only database view. The standalone entry point may optionally be given `--database PATH`; this creates only `MHeardDatabase` plus a P6 diagnostics observer using that read-only source. It does not create or start the P3 SQLite writer. Console display is capped at 100 stations even though the underlying frozen P4 API supports a larger bounded query.

`MCOM`, `MCON`, and `MRPT` bind only to the frozen 0D-P2 in-memory `MonitorPolicyState`. Queries do not mutate policy. Effective `ON`/`OFF` updates use the already-qualified atomic generation-tagged setters and report the resulting generation.

## Deliberately unavailable commands

0E-P1 is not a connected-mode, converse, beacon, KISS-control, or transmit console. The qualification suite explicitly proves that future commands such as these fail as unknown commands:

```text
CONNECT
CONVERSE
UNPROTO
BEACON
TX
SEND
TRANSMIT
KISS
SHELL
```

Those surfaces remain deferred to their roadmap phases and receive no abbreviation or compatibility aliases in P1.

## Safety boundary

0E-P1 adds:

- no TCP or other network listener;
- no Telnet service;
- no PTY allocation;
- no serial-port access;
- no modem owner or modem dependency;
- no KISS session;
- no packet subscriber;
- no worker thread;
- no additional in-memory queue;
- no SQLite database-write capability;
- no retention `apply()` capability;
- no TX capability;
- no GPIO/reset/flash/option-byte path.

The dedicated package smoke test installs the editable package, launches `ywd1278-console`, exercises `VERSION`, unavailable standalone `STATUS`, all three monitor defaults, and clean `QUIT`, with no UART or RF activity.

## Host qualification

Dedicated workflow:

- workflow: `0e-p1-local-console-ci`
- run: `33827541642`
- result: success

The successful dedicated run compiled the new boundary, ran the complete local-console regression suite and architecture contract, exercised the installed console entry point, preserved the frozen 0D-P6 host/target-Pi evidence, preserved frozen 0D-P5/P4/P3 qualification, and preserved the sustained 0C-P8 runtime boundary.

Machine-readable evidence is stored in `firmware/qualification/0e-p1-local-tnc-console-host.json` and enforced by `tests/local_tnc_console_qualification_contract_test.py`.

## Qualification anchors

- `src/ywd1278/console/local.py`
- `tests/local_tnc_console_test.py`
- `tests/local_tnc_console_contract_test.py`
- `tests/local_tnc_console_qualification_contract_test.py`
- `firmware/qualification/0e-p1-local-tnc-console-host.json`
- `.github/workflows/0e-p1-local-console-ci.yml`

P1 intentionally stops at a single local process console. The next independent 0E boundary is the network/Telnet console, which must add bind-address/authentication behavior without weakening this frozen local parser or gaining packet TX capability merely by being network reachable.
