# 0E-P4 virtual PTY/serial TNC personality — host qualified

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P4 is host-qualified at implementation head `aba04bc61810c8038ce6890e6bc9c634088690db` by dedicated GitHub Actions run `33834928723` (`success`). The phase is **not complete** until the same virtual PTY boundary passes a target-Raspberry-Pi smoke test.

## What P4 adds

P4 adds one local kernel pseudo-terminal personality over the frozen 0E-P1 `LocalTNCCommandShell`:

- master/slave PTY created only with `os.openpty()`
- slave appears as `/dev/pts/N`
- slave is put into raw terminal mode and chmod `0600`
- optional stable symlink is explicit, absolute-path-only, refuses to replace any existing object, and is removed on clean close only if it still points to the P4-owned PTY
- `SIGINT` and `SIGTERM` request graceful server shutdown so service-style termination also removes the owned stable link
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

- `src/ywd1278/console/pty_serial.py` — `c0ba2a3278ac1e790bf383fc12a220ae327255ba`
- `tests/pty_serial_tnc_console_test.py` — `8acba59b456b2224dbb0e64b76b7f7ef0bfc4b94`
- `tests/pty_serial_tnc_console_contract_test.py` — `cff343aa56a6c20f9cb539bb95d4765ebdeb1da7`
- `tools/qualify_0e_p4_pty.py` — `1740249933aa0ab8f8201f0bf5b136f86e3c8cbe`
- `src/ywd1278/console/local.py` — `9fed5416ca9123811413f4ef284abff0006a48dd`
- `src/ywd1278/console/telnet.py` — `d15669eb61f2afdf4d0d177191124ef8f13713e0`
- `src/ywd1278/console/auth.py` — `0bdacaca9807012954c3362a8c0d92c4c1e21d40`
- `src/ywd1278/console/lan_telnet.py` — `a53bad81aa3ffa167375517bb48a19e8ac9143f3`
- `pyproject.toml` — `9331c09b7f1e3c7111e437f3007e1e2c14716eb3`

## Host proof

On Ubuntu 24.04.4 / CPython 3.11.16:

- 11/11 P4 regressions passed using real kernel PTYs
- architecture/safety contract passed
- deterministic qualification helper opened a `/dev/pts/N` slave through normal POSIX TTY APIs
- mode `0600` and stable-link create/resolve/cleanup passed
- an actual CLI process received `SIGTERM`, exited normally, and removed its stable link
- detach/reopen monitor-state reset passed
- `QUIT` logical-session reset passed
- future `CONNECT` and `TX` commands stayed rejected
- frozen P3, P2, P1, 0D, and sustained 0C runtime preservation all passed

## Remaining gate

Run the deterministic P4 qualification helper and process-level SIGTERM lifecycle smoke on the actual target Pi from a clean checkout of the evidence-bearing P4 branch. This test is local-only and requires **no HAT, UART, modem, packet traffic, RF, or TX activity**.

Do not mark the roadmap item complete, create the final P4 checkpoint, or merge P4 into `dev` until the target-Pi PTY smoke is recorded separately from this host evidence.
