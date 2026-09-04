# 0E-P4 virtual PTY/serial TNC personality — target Pi qualified

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P4 passed its target-Raspberry-Pi virtual PTY smoke on branch `dev-0e-p4-virtual-pty-console` at tested head `1be7340d920bb64251245b67ce1c4fb32da15486`. The implementation remains anchored to host-qualified implementation head `aba04bc61810c8038ce6890e6bc9c634088690db`, whose dedicated CI run `33834928723` completed successfully.

The target used CPython 3.13.5 and allocated real kernel slave PTY `/dev/pts/1`.

## Target proof

The deterministic helper reported:

- `YWD1278_0E_P4_TARGET_PTY=PASS`
- slave path under `/dev/pts/`
- slave mode `0600`
- normal termios API access passed
- stable-link create/resolve passed
- frozen P1 commands passed
- detach/reopen reset monitor state
- `QUIT` started a fresh logical serial session
- future `CONNECT` and `TX` commands remained rejected
- no network listener was required
- no hardware serial device was opened
- no modem/KISS/TX path was present
- no RF hardware test was required
- stable-link cleanup passed

The helper ran inside a child shell after the earlier interactive-shell qualification wrapper had caused PuTTY to close on error paths. The child exited `0`, `YWD1278_0E_P4_SAFE_TEST=PASS`, and the PuTTY session remained open.

## Evidence scope

The reduced PuTTY-safe target wrapper verified the expected branch/head and successful helper exit, but it did **not** run a separate `git status --porcelain` cleanliness assertion. The target evidence records that limitation explicitly rather than claiming a cleanliness proof that was not printed.

Likewise, the target helper exercised normal deterministic PTY close/link cleanup, not process-level SIGTERM. Actual CLI SIGTERM cleanup is frozen separately in host qualification: implementation head `aba04bc61810c8038ce6890e6bc9c634088690db`, CI run `33834928723`, where the real P4 CLI process received SIGTERM and its stable PTY link was verified removed.

## Frozen P4 implementation

The target evidence pins:

- `src/ywd1278/console/pty_serial.py` — `c0ba2a3278ac1e790bf383fc12a220ae327255ba`
- `tests/pty_serial_tnc_console_test.py` — `8acba59b456b2224dbb0e64b76b7f7ef0bfc4b94`
- `tests/pty_serial_tnc_console_contract_test.py` — `cff343aa56a6c20f9cb539bb95d4765ebdeb1da7`
- `tools/qualify_0e_p4_pty.py` — `1740249933aa0ab8f8201f0bf5b136f86e3c8cbe`

Frozen P1/P2/P3 and `pyproject.toml` blobs remain unchanged as recorded by both host and target evidence contracts.

## Safety boundary

0E-P4 remains a local virtual terminal personality only. It adds no HAT access, hardware UART/serial transport, TCP/UDP listener, modem owner, KISS session, TX broker, GPIO, flash, or RF activity. `CONNECT`, `CONVERSE`, `UNPROTO`, `BEACON`, `TX`, `SEND`, `TRANSMIT`, `KISS`, and `SHELL` remain future commands and are not enabled by P4.

No HAT or RF requalification was performed or required for this phase.
