# 0E-P5 classic TNC2/MFJ vocabulary — target Pi qualification

Date: 2026-09-03 (America/Los_Angeles)

## Result

0E-P5 is target-Pi qualified over the already-qualified 0E-P4 virtual PTY/serial personality.

The target Pi tested branch `dev-0e-p5-classic-vocabulary` at exact SHA `a0d102778c9da3be180dcdae7c1f455f66e72e91`. The branch was already up to date, the working tree was clean before qualification, and the working tree remained clean afterward.

The host-qualified implementation remains pinned separately at `ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3`, dedicated CI run `33836726120` (`success`). The earlier host evidence remains immutable historical evidence and still truthfully records the target smoke as pending at the time that host record was frozen.

## Target environment

- Python: 3.13.5
- Kernel: `Linux pi5-norm 6.18.34+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.18.34-1+rpt1 (2026-06-09) aarch64 GNU/Linux`
- Real kernel PTY slave: `/dev/pts/1`
- PTY slave mode: `0600`
- normal `termios` API access: PASS

## Target regression and composition proof

All 10 0E-P5 vocabulary regressions passed on the target Pi. Those tests include composition through the frozen 0E-P2 loopback Telnet transport and through the frozen 0E-P4 real kernel PTY transport.

The target also passed the 0E-P5 architecture contract and the frozen 0E-P5 host-evidence contract before running the deterministic PTY qualification helper.

The helper proved:

- safe aliases `DISP`, `MH`, `VER`, `STAT`, and `HEAL` work through the real P4 PTY;
- `DISPLAY`/`DISPLAY MONITOR` reports only the real supported monitor parameters `MCOM`, `MCON`, and `MRPT`;
- detach/reopen resets per-session monitor state;
- ambiguous abbreviations fail closed rather than being guessed;
- `CONNECT`, `CONVERSE`, `UNPROTO`, and `BEACON` are recognized but remain deferred;
- `TX`, `XMITOK`, and `KISS` are recognized but remain deferred;
- `MHCLEAR` remains explicitly disabled at the read-only MHEARD boundary;
- the temporary stable PTY link is removed during cleanup.

## Safety boundary

0E-P5 is a vocabulary adapter only. It does not add a network listener, PTY owner, hardware-serial/UART open, modem owner, KISS session, database writer, retention apply path, TX broker, GPIO activity, RF activity, firmware flash, or any TX path.

No HAT, UART, RF, or 145.050 MHz physical test is required for this phase. TX/link commands are vocabulary-recognized but non-operational and remain owned by later 0F/0G or product-control phases.

## PuTTY-safe wrapper

The target qualification was run inside a child Bash process so any assertion failure could not terminate the operator's PuTTY login shell. The child exited `0`, reported `YWD1278_0E_P5_SAFE_TEST=PASS`, and the PuTTY session remained open.

## Qualification markers

```text
YWD1278_0E_P5_TARGET_CLASSIC=PASS
PTY_SLAVE=/dev/pts/1
PTY_SLAVE_MODE=0600
PTY_TERMIOS_API=PASS
SAFE_ALIASES=DISP_MH_VER_STAT_HEAL
DISPLAY_MONITOR=PASS
DETACH_REOPEN_STATE_RESET=PASS
AMBIGUOUS_ABBREVIATIONS=FAIL_CLOSED
CONNECT_CONVERSE_UNPROTO_BEACON=DEFERRED
TX_XMITOK_KISS=DEFERRED
MHCLEAR=DISABLED_READ_ONLY
FROZEN_P4_PTY_COMPOSITION=PASS
HARDWARE_SERIAL_OPENED=NO
MODEM_KISS_TX_PATH=ABSENT
TX_RF_HARDWARE_TEST_REQUIRED=NO
STABLE_LINK_CLEANUP=PASS
P5_TREE_CLEAN=PASS
P5_TESTED_SHA=a0d102778c9da3be180dcdae7c1f455f66e72e91
YWD1278_0E_P5_TARGET_PI=PASS
CHILD_TEST_EXIT_CODE=0
YWD1278_0E_P5_SAFE_TEST=PASS
PUTTY_SESSION_STILL_ALIVE=YES
```

This closes the target-Pi gate for 0E-P5.
