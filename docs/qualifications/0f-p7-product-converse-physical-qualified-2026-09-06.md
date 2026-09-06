# 0F-P7 Product Converse Physical Qualification — 2026-09-06

Status: **PHYSICALLY QUALIFIED**

This qualification advances the permanent product-console composition only. Historical 0F-P4 classic-TX evidence remains frozen and unchanged.

## Tested source

- `dev` commit: `4971a0d332cd154ea0d5fdfc8e23949496549f94`
- tree: `d7452afdf855dc34c0705dcad15b48af6dff9f79`
- staged source was executed from a detached checkout; the installed appliance source was not replaced for the test.
- installed RX-safe recovery baseline remained `b10bae526c9f21ee36d6531dfbb44feb0816fd24`.

## Pre-arm safety baseline

- persistent config SHA-256: `2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76`
- persistent TX: disabled
- persistent beacon: disabled
- exact AX25R4 qualified firmware artifact used by the appliance
- no firmware write
- no option-byte write

## Qualified RF vector

- frequency: `145.050 MHz`
- source: `KJ6YWD-10`
- destination: `YWD127`
- path: direct
- control: AX.25 UI
- PID: `F0`
- information: `YWD-1278 PRODUCT CONVERSE 1/1`
- expected external decode: `KJ6YWD-10>YWD127:YWD-1278 PRODUCT CONVERSE 1/1`

An independent receiver decoded the exact frame once. A screenshot of that independent decode was observed during qualification; the raw screenshot is intentionally not archived in the repository.

## Product-session behavior proved

The permanent product Telnet console entered `CONVERSE`, suppressed the command prompt while conversing, and accepted exactly one line of user text into the existing product TX admission path.

Physical accounting after the transmission:

- product converse TX lines: `1`
- KISS TX messages: `0`
- TX dispatches: `1`
- TX queue accepted: `1`
- TX queue dispatched: `1`
- subscriber drops: `0`
- automatic TX retry: `NO`
- second internal dispatch after hold: `NO`

The same Telnet converse session then displayed a fresh live RF packet:

`RX KJ6YWD>JIM:yooooooooo hellooooooo`

`/CMD` returned the session to command mode and restored the `cmd:` prompt.

## Final safety state

The qualifier completed successfully with:

- `YWD1278_0F_PRODUCT_CONVERSE_PHYSICAL=PASS`
- `PRODUCT_CONVERSE_TX_LINES=1`
- `INDEPENDENT_EXTERNAL_DECODE_COUNT=1`
- `PRODUCT_CONVERSE_LIVE_RX=PASS`
- `PRINTABLE_CMD_ESCAPE=PASS`
- `COMMAND_PROMPT_RESTORED=PASS`
- `AUTOMATIC_TX_RETRY=NO`
- `PERSISTENT_TX_ENABLED=NO`
- `PERSISTENT_CONFIG_MUTATED=NO`
- `INSTALLED_SOURCE_MUTATED=NO`
- `NORMAL_SERVICE_RESTORED=YES`
- `FLASH_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

The normal qualified RX-safe service was restored after the staged physical test.

## Scope boundary

0F-P7 physically qualifies **one direct UNPROTO UI transmission from the permanent product Telnet converse session**, same-session live RX display, printable `/CMD` escape, and single-dispatch/no-retry/restoration behavior.

This slice does **not** physically qualify persistent TX enablement, sustained multi-line RF converse operation, raw Ctrl-C as a physical terminal escape, product-session VIA/digipeater RF routing, beacon/BTEXT/ID RF behavior, or connected-mode `CONNECT` behavior.
