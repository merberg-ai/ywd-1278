# 0E-P3 Target-Pi Authenticated LAN Console Qualification

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P3 authenticated private-LAN console behavior is target-Pi qualified.

The qualified implementation remains the host-qualified 0E-P3 implementation at:

`dd58fbd3f1eade8227c0514751046201d2fb1e07`

The real private-LAN smoke was staged from branch `dev-0e-p3-auth-lan-console` at:

`1da631ca2c9dca8359c8d0655fb82259708355c8`

## Physical network path exercised

- Target Raspberry Pi: `192.168.1.11:8023`
- Remote LAN host source: `192.168.1.15`
- Both endpoints were RFC1918 IPv4 addresses.
- The remote source was a separate host from the target Pi.
- Transport remained plaintext Telnet and the console displayed the explicit `NOT encrypted` warning.

## Authentication proof

Before authentication the remote client received only the 0E-P3 banner and `Username:` prompt; command mode was not exposed.

An intentionally incorrect password produced `AUTH FAIL 1/3` and returned to `Username:` without exposing `cmd:`.

Valid credentials produced `AUTH OK` and only then entered the unchanged P1 command shell.

Reconnect required authentication again before command mode was available.

The temporary credential file was mode `0600` and contained only the qualified PBKDF2-SHA256 verifier format. No plaintext password persistence was qualified or introduced.

## Frozen P1 behavior proved over the LAN

The authenticated remote session returned:

- `VERSION` -> `YWD-1278 0.1.0-alpha0`
- `MCOM` -> `MCOM OFF`
- `MCON` -> `MCON OFF`
- `MRPT` -> `MRPT ON`
- `MCOM ON` -> `MCOM ON` and `MONITOR_GENERATION 1`
- `CONNECT KJ6YWD` -> `ERROR UNKNOWN COMMAND CONNECT`
- `TX hello` -> `ERROR UNKNOWN COMMAND TX`
- `QUIT` -> `BYE`

A second authenticated connection returned `MCOM OFF`, proving monitor-policy state reset across reconnect.

## Bind safety proof

The target Pi listener was bound specifically to `192.168.1.11:8023`; there was no active `0.0.0.0:8023` wildcard listener.

Explicit attempts to bind to both `0.0.0.0` and `8.8.8.8` failed with the 0E-P3 private-address restriction.

## Cleanup-harness observation

The historical/manual final-Pi block reported stale saved PID `100200` while `ss` showed the actual live listener at PID `100607`.

This did not invalidate the qualification because the subsequent separate-host remote test successfully exercised the live `192.168.1.11:8023` listener and proved the authentication/session boundary end-to-end. However, the stale PID means the historical cleanup block could not prove that the live listener itself was terminated. The qualification evidence therefore records a cleanup follow-up requirement rather than hiding the anomaly.

This is a qualification-harness cleanup issue only; it does not alter the frozen 0E-P3 implementation or the observed authentication/bind behavior.

## Safety boundary retained

0E-P3 still adds no:

- PTY or serial personality
- database-write or retention-apply capability
- KISS session
- packet subscriber
- modem dependency
- TX capability
- UART activity
- RF activity

No TX/RF hardware test was required for this phase.

## Evidence

Machine-readable target evidence:

`firmware/qualification/0e-p3-auth-lan-console-target-pi.json`

Immutable evidence contract:

`tests/auth_lan_console_target_pi_evidence_contract_test.py`
