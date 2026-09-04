# 0E-P5 classic TNC2/MFJ-style command vocabulary — host qualified

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P5 is host-qualified at implementation head `ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3` by dedicated GitHub Actions run `33836726120` (`success`). The phase is **not complete** until the same vocabulary adapter passes its deterministic target-Raspberry-Pi smoke through the already-qualified 0E-P4 virtual PTY.

## Historical command basis

The compatibility surface follows familiar TNC2/MFJ command naming rather than inventing a new vocabulary. Period TAPR TNC-2 documentation describes `DISPLAY` as the parameter-display command, `MHEARD` as the heard-station list, and the familiar monitor controls `MCOM`, `MCON`, `MONITOR`, and `MRPT`.

P5 intentionally does **not** attempt full vintage-firmware emulation. It adds only commands that can be represented truthfully over already-qualified YWD-1278 state, and it recognizes later-phase commands without activating them.

## What P5 adds

`ClassicTNCCommandShell` subclasses the frozen 0E-P1 `LocalTNCCommandShell`. The P1 parser itself is unchanged.

Explicit safe aliases:

- `DISP` -> `DISPLAY`
- `MH` -> `MHEARD`
- `VER` -> `VERSION`
- `STAT` -> `STATUS`
- `HEAL` -> `HEALTH`

`DISPLAY` and `DISPLAY MONITOR` show only real session monitor parameters that already exist:

- `MCOM`
- `MCON`
- `MRPT`

There is deliberately no generic abbreviation engine. Ambiguous forms such as `D`, `C`, `CON`, `MCO`, `UNP`, and `XMIT` fail closed as unknown commands.

## Recognized but deferred vocabulary

P5 recognizes familiar commands so an operator gets a deterministic explanation instead of accidentally assuming they are implemented.

0F-owned UI/unproto/converse/beacon vocabulary remains inert, including `UNPROTO`, `CONVERSE`, `BEACON`, `BTEXT`, and `ID`.

0G-owned connected-mode vocabulary remains inert, including `CONNECT`, `DISCONNECT`, `RECONNECT`, `CSTATUS`, `CONMODE`, `CONOK`, `CONPERM`, `MAXFRAME`, `PACLEN`, `RETRY`, `TRIES`, `FRACK`, and `RESPTIME`.

Later configuration/parameter/mode controls also remain inert, including `MYCALL`, `MYALIAS`, `DIGIPEAT`, `MONITOR`, `MALL`, `PASSALL`, `TXDELAY`, `PERSIST`, `SLOTTIME`, `FULLDUP`, `FULLDUPLEX`, `XMITOK`, `KISS`, `TX`, `SEND`, and `TRANSMIT`.

Destructive or escape-style commands are explicitly disabled: `MHCLEAR`, `RESET`, `RESTART`, and `SHELL`.

## Host proof

Dedicated CI proved:

- 10/10 P5 regressions passed
- P5 architecture/safety contract passed
- exact P1 commands remain unchanged through the subclass
- all safe aliases behave deterministically
- `DISPLAY` is bounded to the real MCOM/MCON/MRPT state
- deferred TX/link/config commands remain inert
- destructive commands remain disabled
- ambiguous abbreviations fail closed
- a real frozen P2 localhost Telnet server accepted the P5 subclass and served `DISP`
- a real frozen P4 kernel PTY accepted the P5 subclass, served classic commands, rejected/deferred TX vocabulary, and reset monitor state across detach/reopen
- the deterministic P5 target helper passed on the host Linux runner
- frozen P4, P3, P2, P1, 0D, and sustained 0C qualification gates all remained green

## Frozen boundaries

The host evidence freezes the exact P5 implementation/test/helper blobs and preserves these exact older boundaries:

- `src/ywd1278/console/local.py` — `9fed5416ca9123811413f4ef284abff0006a48dd`
- `src/ywd1278/console/telnet.py` — `d15669eb61f2afdf4d0d177191124ef8f13713e0`
- `src/ywd1278/console/auth.py` — `0bdacaca9807012954c3362a8c0d92c4c1e21d40`
- `src/ywd1278/console/lan_telnet.py` — `a53bad81aa3ffa167375517bb48a19e8ac9143f3`
- `src/ywd1278/console/pty_serial.py` — `c0ba2a3278ac1e790bf383fc12a220ae327255ba`
- `pyproject.toml` — `9331c09b7f1e3c7111e437f3007e1e2c14716eb3`

## Explicit non-capabilities

P5 adds no network listener or PTY owner of its own. It adds no hardware serial access, database write, retention apply, modem owner, KISS session, TX broker, UART traffic, RF activity, GPIO access, or firmware/flash path.

## Remaining gate

Run the deterministic P5 helper on the actual target Pi from a clean checkout of the evidence-bearing P5 branch. This is a local software/PTY test only. No HAT, UART, modem, packet traffic, RF, or TX activity is required.
