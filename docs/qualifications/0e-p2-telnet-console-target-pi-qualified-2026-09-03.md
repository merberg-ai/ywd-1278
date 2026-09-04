# 0E-P2 Telnet command console — target-Pi qualification

Date: 2026-09-03 (America/Los_Angeles)

Status: **target-Pi qualified**

## Tested source

Branch:

```text
dev-0e-p2-telnet-console
```

Exact tested SHA:

```text
9f1e08a8c9aa5c3ffe7e96612a34cf7384fd6771
```

The target checkout was clean before qualification.

The tested SHA had already passed the dedicated `0e-p2-telnet-console-ci` workflow as run:

```text
33830066688
```

The frozen host-qualified implementation identity remains:

```text
37bcc6808e5287bfd49ba37d56b1a7d5185f8b1c
```

with original dedicated host qualification run:

```text
33829902701
```

## Target-Pi contract result

The target Pi ran the 0E-P2 regression and architecture/qualification contracts directly from the checked-out source.

Result:

```text
14 tests run
14 tests passed
```

The architecture contract reported:

```text
YWD1278_0E_P2_TELNET_CONSOLE_CONTRACT=PASS
FROZEN_0E_P1_BLOBS=PASS
TELNET_BIND_IPV4_LOOPBACK_ONLY=YES
P1_PARSER_REUSED=YES
P1_PARSER_MODIFIED=NO
REMOTE_OR_WILDCARD_BIND=ABSENT
MODEM_UART_KISS_TX_CAPABILITY=ABSENT
RF_ACTIVITY=NONE
```

The immutable host qualification contract also passed on the target Pi.

## Live loopback session

The target launched the P2 listener with:

```bash
PYTHONPATH=src python3 -u -m ywd1278.console.telnet \
    --bind 127.0.0.1 \
    --port 8023
```

Server log:

```text
YWD-1278 0E-P2 Telnet console listening on 127.0.0.1:8023
Loopback-only host gate; no remote/LAN exposure is permitted in this phase.
```

The first live socket session received the expected banner:

```text
YWD-1278 0.1.0-alpha0 TELNET TNC CONSOLE
0E-P2 loopback-only command mode; type HELP for commands.
cmd:
```

The following commands were exercised through the live loopback socket:

```text
VERSION
STATUS
HEALTH
MHEARD
MCOM
MCON
MRPT
MCOM ON
CONNECT KJ6YWD
TX hello
QUIT
```

Observed qualified behavior:

```text
VERSION -> YWD-1278 0.1.0-alpha0
STATUS -> STATUS UNAVAILABLE
HEALTH -> HEALTH UNAVAILABLE
MHEARD -> MHEARD UNAVAILABLE
MCOM -> OFF
MCON -> OFF
MRPT -> ON
MCOM ON -> ON / MONITOR_GENERATION 1
CONNECT KJ6YWD -> ERROR UNKNOWN COMMAND CONNECT
TX hello -> ERROR UNKNOWN COMMAND TX
QUIT -> BYE
```

This proves that the network session feeds the frozen P1 command parser rather than introducing a parallel parser or enabling future transmit-bearing commands.

## Disconnect/reconnect state proof

A second loopback connection was then opened after the first session changed `MCOM` to `ON`.

The second session reported:

```text
MCOM OFF
```

This proves that the 0E-P2 monitor policy is session-local and resets to the frozen P1 defaults across disconnect/reconnect.

## Non-loopback fail-closed proof

The target then attempted:

```bash
PYTHONPATH=src python3 -m ywd1278.console.telnet \
    --bind 0.0.0.0 \
    --port 8024
```

The listener refused to start and reported:

```text
0E-P2 listener is restricted to IPv4 loopback addresses
```

The wildcard bind was therefore rejected exactly as designed.

## Final target result

```text
YWD1278_0E_P2_TARGET_PI_LOOPBACK_SESSION=PASS
P1_COMMAND_PARSER_REUSED=YES
SESSION_RECONNECT_POLICY_RESET=PASS
FUTURE_TX_COMMANDS_REJECTED=PASS
YWD1278_0E_P2_TARGET_PI=PASS
TELNET_LOOPBACK_ONLY=PASS
WILDCARD_BIND_REJECTED=PASS
TX_RF_HARDWARE_TEST_REQUIRED=NO
```

## Safety boundary preserved

This target qualification did not require or add:

- non-loopback listener exposure
- authentication
- PTY allocation
- serial-port personality
- modem ownership or modem dependency
- KISS session
- packet subscriber
- SQLite writer
- retention apply path
- transmit broker
- TX capability
- UART activity
- RF activity
- GPIO/reset/flash/option-byte activity

No RF or HAT-side requalification is required for 0E-P2 because this phase remains a host-side operator/network-console layer only.

## Qualification conclusion

0E-P2 is qualified on the target Pi for the loopback-only Telnet boundary.

Broader LAN/public binding remains intentionally unavailable. Authentication and bind-address hardening must be qualified separately before any non-loopback exposure is permitted.
