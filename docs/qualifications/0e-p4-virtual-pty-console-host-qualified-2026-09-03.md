# 0E-P4 virtual PTY/serial TNC personality — host qualified

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P4 is host-qualified at implementation head `2f8bf6aff6cc95c7553a6344ac0d7313c1d21ba4` by dedicated GitHub Actions run `33834614216` (`success`). The phase is **not complete** until the same virtual PTY boundary passes a target-Raspberry-Pi smoke test.

## What P4 adds

P4 adds one local kernel pseudo-terminal personality over the frozen 0E-P1 `LocalTNCCommandShell`:

- master/slave PTY created only with `os.openpty()`
- slave appears as `/dev/pts/N`
- slave is put into raw terminal mode and chmod `0600`
- optional stable symlink is explicit, absolute-path-only, refuses to replace any existing object, and is removed on clean close only if it still points to the P4-owned PTY
- bounded printable-ASCII command stream with CR/LF, backspace and TAB handling
- 256-character command-line cap inherited from P1
- default 1024-command logical-session cap, hard cap 10000
- physical slave detach/reopen constructs a fresh P1 shell and resets monitor policy
- `QUIT`/`EXIT` starts a fresh logical serial session without terminating the P4 server process

No new command vocabulary is added. `CONNECT`, `CONVERSE`, `UNPROTO`, `BEACON`, `TX`, `SEND`, `TRANSMIT`, `KISS`, and `SHELL` remain rejected by frozen P1.

## Explicit non-capabilities

P4 does **not** add or open:

- a TCP/UDP listener
- `/dev/ttyAMA0`, `/dev/serial0`, or another hardware serial path
- pyserial
- the MMDVM modem owner or POSIX modem transport
- KISS session ingress
- TX broker / CSMA dispatch
- SQLite write or retention apply
- GPIO, firmware flash, UART traffic, or RF activity

The optional MHEARD/status database remains the same read-only P1 composition.

## Frozen boundaries

P4 host qualification preserves these exact Git blobs:

- `src/ywd1278/console/local.py` — `9fed5416ca9123811413f4ef284abff0006a48dd`
- `src/ywd1278/console/telnet.py` — `d15669eb61f2afdf4d0d177191124ef8f13713e0`
- `src/ywd1278/console/auth.py` — `0bdacaca9807012954c3362a8c0d92c4c1e21d40`
- `src/ywd1278/console/lan_telnet.py` — `a53bad81aa3ffa167375517bb48a19e8ac9143f3`
- `pyproject.toml` — `9331c09b7f1e3c7111e437f3007e1e2c14716eb3`

The P4 implementation/test/helper blobs are frozen in `firmware/qualification/0e-p4-virtual-pty-console-host.json`.

## Host proof

On Ubuntu 24.04.4 / CPython 3.11.16:

- 11/11 P4 regressions passed using real kernel PTYs
- architecture/safety contract passed
- deterministic qualification helper opened `/dev/pts/0` through normal POSIX TTY APIs
- mode `0600` and stable-link create/resolve/cleanup passed
- detach/reopen monitor-state reset passed
- `QUIT` logical-session reset passed
- future `CONNECT` and `TX` commands stayed rejected
- frozen P3, P2, P1, 0D, and sustained 0C runtime preservation all passed

## Remaining gate

Run the deterministic P4 qualification helper on the actual target Pi from a clean checkout of the evidence-bearing P4 branch. This test is local-only and requires **no HAT, UART, modem, packet traffic, RF, or TX activity**.

Do not mark the roadmap item complete, create the final P4 checkpoint, or merge P4 into `dev` until the target-Pi PTY smoke is recorded separately from this host evidence.
