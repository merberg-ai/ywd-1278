# 0E-P2 Telnet command console — host qualification

Date: 2026-09-03 (America/Los_Angeles)

Status: **host-qualified; target-Pi loopback smoke pending**

## Qualified boundary

0E-P2 adds a bounded IPv4-loopback Telnet session layer above the frozen 0E-P1 `LocalTNCCommandShell` parser.

The network layer does not duplicate or extend command parsing. Each accepted connection receives a fresh P1 shell instance. `MCOM`, `MCON`, and `MRPT` therefore remain session-local for this host gate; disconnect/reconnect restores the qualified P1 defaults.

The implementation is intentionally restricted to literal IPv4 loopback addresses. The default listener is:

```text
127.0.0.1:8023
```

Wildcard, LAN, public, hostname, and IPv6 binds are rejected. Authentication is therefore not yet present in this slice; a broader bind must not be enabled until a separate authentication/bind-address gate is designed and qualified.

## Bounds

Qualified defaults and hard limits:

```text
command line:              256 characters
receive chunk:             512 bytes
default clients:           4
hard client cap:           16
default idle timeout:      300 seconds
default session lifetime:  3600 seconds
default command cap:       1024 commands
hard command cap:          10000 commands
Telnet negotiations:       32 per session
```

Telnet WILL/WONT/DO/DONT requests are refused. Unsupported Telnet controls, NUL data, and invalid NVT control bytes fail closed. Oversized lines are bounded, discarded through the line terminator, reported once, and the next line can be parsed normally.

## Frozen P1 preservation

Base checkpoint:

```text
checkpoint/0e-p1-local-tnc-console-host-qualified
c51484fce731fea0bb62ab923f3aa66ef214a1b5
```

The frozen P1 parser remains exact:

```text
src/ywd1278/console/local.py
9fed5416ca9123811413f4ef284abff0006a48dd
```

The frozen package manifest also remains exact:

```text
pyproject.toml
9331c09b7f1e3c7111e437f3007e1e2c14716eb3
```

For that reason this stage deliberately uses the module launch surface:

```bash
PYTHONPATH=src python3 -m ywd1278.console.telnet
```

No new installed script entry point was added because changing `pyproject.toml` would invalidate the immutable 0E-P1 qualification contract.

## Dedicated CI

Qualified implementation head:

```text
37bcc6808e5287bfd49ba37d56b1a7d5185f8b1c
```

Dedicated workflow:

```text
0e-p2-telnet-console-ci
```

Successful run:

```text
33829902701
```

The run passed:

- Python compile checks for the P2 module/tests
- live localhost socket regression tests
- Telnet negotiation/refusal tests
- oversized-line recovery
- malformed-control fail-closed behavior
- maximum-client rejection without disturbing an active session
- idle timeout
- command-count limit
- disconnect/reconnect session-state reset
- architecture/safety contract
- module entry-point smoke
- frozen 0E-P1 regression and immutable qualification contract
- frozen 0D-P1 through P6 qualification preservation
- frozen sustained 0C TNC runtime preservation

## Safety boundary

0E-P2 host qualification adds a bounded loopback TCP/Telnet listener and bounded per-client session threads only.

It adds no:

- non-loopback listener
- authentication surface yet
- PTY
- serial personality
- modem owner or modem dependency
- KISS session
- packet subscriber
- SQLite writer
- retention apply path
- transmit broker
- TX capability
- UART activity
- RF activity
- GPIO/reset/flash/option-byte activity

Future transmit-bearing classic commands remain rejected by the unchanged P1 parser:

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

## Next qualification step

Run a target-Pi loopback smoke from the P2 branch, connect locally to `127.0.0.1:8023`, exercise the frozen P1 command vocabulary, verify session-local monitor state across reconnect, and prove that a non-loopback bind is rejected.

Do not expose the Telnet listener to the LAN or a public interface in this host-qualified slice.
