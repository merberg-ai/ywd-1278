# 0E-P3 authenticated LAN TNC console — host qualification

Date: 2026-09-03 (America/Los_Angeles)

Status: **host-qualified; target-Pi private-LAN smoke pending**

## Qualified boundary

0E-P3 adds an authenticated private-LAN Telnet console without modifying the frozen 0E-P2 Telnet implementation or the frozen 0E-P1 command parser.

The composition is:

```text
private IPv4 client
        |
        v
bounded P3 listener / source-address gate
        |
        v
mandatory authentication
        |
        v
frozen P2 Telnet decoder and session limits
        |
        v
fresh frozen P1 LocalTNCCommandShell
```

The P1 shell is not constructed until authentication succeeds. Failed authentication, authentication timeout, and authentication-attempt exhaustion therefore cannot reach the command parser.

## Network exposure policy

The safe default remains:

```text
127.0.0.1:8023
```

A non-loopback bind is accepted only when the operator explicitly supplies a literal IPv4 address inside one of the RFC1918 ranges:

```text
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
```

The accepted client source address is independently checked against the same loopback/RFC1918 policy.

The following remain rejected:

- wildcard `0.0.0.0`
- public IPv4 addresses
- CGNAT `100.64.0.0/10`
- IPv4 link-local addresses
- hostnames
- IPv6

**Telnet is not encrypted.** This stage is qualified only for a trusted/private LAN. It is not approved for WAN exposure, router port forwarding, a public IP, or an untrusted network.

## Authentication policy

Credentials are stored in one protected local file as:

```text
username:pbkdf2-sha256$iterations$salt$verifier
```

Qualified credential policy:

```text
hash:                   PBKDF2-HMAC-SHA256
default iterations:     310000
minimum iterations:     200000
maximum iterations:     1000000
salt:                   16 random bytes
digest:                 32 bytes
username:               1..32 restricted ASCII characters
password:               10..128 printable ASCII characters
auth file maximum:      1024 bytes
auth file permissions:  0600
symlink following:      rejected
plaintext persistence:  none
```

The credential helper prompts through `getpass`; it does not require the password as a command-line argument.

Authentication session limits:

```text
default auth timeout:   30 seconds
maximum auth timeout:   300 seconds
default attempts:       3
hard attempt cap:       5
```

Every reconnect requires authentication again.

## Frozen lower-layer preservation

Base checkpoint:

```text
checkpoint/0e-p2-telnet-console-target-pi-qualified
ef374e86b36ba4252d899acbe211084e293b190f
```

Frozen P2 Telnet module:

```text
src/ywd1278/console/telnet.py
d15669eb61f2afdf4d0d177191124ef8f13713e0
```

Frozen P1 parser:

```text
src/ywd1278/console/local.py
9fed5416ca9123811413f4ef284abff0006a48dd
```

Frozen package manifest:

```text
pyproject.toml
9331c09b7f1e3c7111e437f3007e1e2c14716eb3
```

0E-P3 does not add an installed console-script entry point because modifying the frozen package manifest would invalidate the earlier qualification contract.

## Host-qualified implementation

Qualified implementation head:

```text
dd58fbd3f1eade8227c0514751046201d2fb1e07
```

Implementation/test blobs:

```text
src/ywd1278/console/auth.py
0bdacaca9807012954c3362a8c0d92c4c1e21d40

src/ywd1278/console/lan_telnet.py
a53bad81aa3ffa167375517bb48a19e8ac9143f3

tests/auth_lan_console_test.py
b25c7753cec4ec8c0f8136a230e59a35b6ae8a41

tests/auth_lan_console_contract_test.py
49fd1c2c5774aaa4744335a98532e2f6aced3eff
```

Dedicated CI:

```text
0e-p3-auth-lan-console-ci
run 33832163068 — success
```

The run passed 11/11 P3 regression tests, including:

- salted hash creation and verification
- malformed credential rejection
- protected auth-file permissions
- auth-file symlink rejection
- RFC1918/loopback bind policy
- RFC1918/loopback client-source policy
- failed authentication cannot construct a P1 shell
- authentication timeout cannot construct a P1 shell
- authentication-attempt exhaustion cannot construct a P1 shell
- active unauthenticated sessions still consume the bounded client slots
- authenticated live localhost session
- fresh authentication on reconnect
- session-local monitor policy reset on reconnect
- `CONNECT` and `TX` remain rejected

The same run also passed the P3 architecture contract, explicit wildcard/public bind rejection, frozen 0E-P2/P1 qualification preservation, frozen 0D qualification preservation, and sustained 0C runtime preservation.

## Safety boundary

0E-P3 adds no:

- PTY
- virtual serial personality
- database writer
- retention apply path
- modem owner or dependency
- KISS session
- packet subscriber
- transmit broker
- TX capability
- UART activity
- RF activity
- GPIO/reset/flash/option-byte activity

The unchanged P1 parser continues to reject future transmit-bearing commands including:

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

Run the exact evidence-bearing P3 head on the target Raspberry Pi, bind the listener to the Pi's literal RFC1918 address, and connect from a **different host on the same private LAN**.

The target test must prove:

1. the auth file is protected and contains only a verifier;
2. the listener is bound to the selected private address, not wildcard;
3. an incorrect password fails without exposing `cmd:`;
4. a correct password reaches the frozen P1 console;
5. future TX-bearing commands remain rejected;
6. disconnect/reconnect requires authentication again and resets session monitor policy;
7. wildcard/public binds still fail closed;
8. no HAT/UART/RF test is required.

Do not merge or mark 0E-P3 complete until that separate-host LAN smoke passes.
