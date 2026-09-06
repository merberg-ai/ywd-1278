# 0F-P8 Sustained Product Converse Physical Qualification — 2026-09-06

Status: **PHYSICALLY QUALIFIED**

This qualification advances the permanent product Telnet `CONVERSE` surface beyond the frozen 0F-P7 one-line/direct-path boundary. Historical P7 and earlier physical evidence remain unchanged.

## Tested source

- staged branch: `dev-0f-p8-sustained-product-converse`
- exact staged source commit physically exercised: `ec308286ae5d7ac8de5c45e782b14e3a87db96f6`
- qualified P8 physical harness blob: `985990dd4395804f605d9c4bde2b8864c46fc05d`
- P8 physical-staging contract blob: `13ddde075f3cab4b70a6db67b166f64a85e73135`
- installed RX-safe recovery baseline remained `b10bae526c9f21ee36d6531dfbb44feb0816fd24`

## Pre-arm safety baseline

- persistent config SHA-256: `2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76`
- persistent TX: disabled
- persistent beacon: disabled
- exact supported HAT identity rechecked before RF
- no firmware write
- no option-byte write
- installed source not mutated

## Qualified RF profile

- frequency: `145.050 MHz`
- TX power: `200/255`
- source: `KJ6YWD-10`
- UNPROTO destination: `JIM`
- VIA path: `YWDNOD`
- TX origin: `PRODUCT_TELNET_CONVERSE`

The three exact product-converse lines were:

1. `KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 1/3`
2. `KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 2/3`
3. `KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 3/3`

The operator confirmed an independent receiver decoded all three exact source frames at least once each. The qualification records a count of `3`; no raw independent-receiver log is archived in the repository.

## Sustained product-session behavior proved

The permanent product Telnet console entered `CONVERSE`, suppressed the command prompt, attached the live RX subscriber, and accepted three distinct user lines through the existing product TX admission/channel-access path.

Physical accounting after the three transmissions:

- product converse TX lines: `3`
- TX dispatches: `3`
- TX queue accepted: `3`
- TX queue dispatched: `3`
- subscriber drops: `0`
- automatic TX retry: `NO`
- second internal dispatch after hold: `NO`

The same converse session then rendered a live received packet:

`RX KJ6YWD-10>JIM,YWDNOD*:YWD-1278 P8 CONVERSE 2/3`

The `YWDNOD*` marker is consistent with a returned digipeated copy of the second P8 frame and, regardless of origin, satisfies the staged same-session live-RX gate after sustained TX.

Printable `/CMD` returned to command mode and restored `cmd:`.

The physical raw Ctrl-C gate also passed:

- raw Ctrl-C returned the session to command mode
- an unfinished partial converse line was discarded
- the partial line did not leak into the next command
- Ctrl-C caused `0` additional TX dispatches

## Final safety state

The qualifier completed with:

- `YWD1278_0F_P8_SUSTAINED_PRODUCT_CONVERSE_PHYSICAL=PASS`
- `PRODUCT_CONVERSE_TX_LINES=3`
- `INDEPENDENT_EXTERNAL_DECODE_COUNT=3`
- `PRODUCT_CONVERSE_LIVE_RX=PASS`
- `PRINTABLE_CMD_ESCAPE=PASS`
- `CTRL_C_ESCAPE=PASS`
- `CTRL_C_PARTIAL_LINE_DISCARD=PASS`
- `CTRL_C_ADDITIONAL_TX=0`
- `AUTOMATIC_TX_RETRY=NO`
- `PERSISTENT_TX_ENABLED=NO`
- `PERSISTENT_CONFIG_MUTATED=NO`
- `INSTALLED_SOURCE_MUTATED=NO`
- `NORMAL_SERVICE_RESTORED=YES`
- `FLASH_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

The normal qualified RX-safe appliance was restored after the staged physical test.

## Scope boundary

0F-P8 physically qualifies a bounded three-line permanent product Telnet `CONVERSE` session, one `VIA YWDNOD` UNPROTO path, three independently decoded over-air source frames, same-session live RX after sustained TX, printable `/CMD`, raw Ctrl-C escape with partial-line discard, zero Ctrl-C-triggered TX, no automatic retry, and restoration of the persistent RX-safe appliance.

This slice does **not** qualify persistent TX enablement, arbitrary/unbounded sustained converse operation, multiple or chained digipeater paths beyond `YWDNOD`, beacon/BTEXT/ID RF behavior beyond their separately frozen qualifications, or connected-mode `CONNECT` behavior.
