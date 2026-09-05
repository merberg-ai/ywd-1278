# YWD-1278 Stage I — single-shot product TX acceptance staging

Date: 2026-09-04 (America/Los_Angeles)

## Status

**HOST STAGING IN PROGRESS — PHYSICAL TX NOT YET EXECUTED.**

Stage I begins only after the final fresh-Raspberry-Pi-OS Stage-H checkpoint:

- `checkpoint/product-fresh-os-stage-h-qualified`
- `e7e203ba6ef76a0465ff6c25ef9671a46a4ab582`

The operator explicitly authorized the Stage-I physical TX acceptance stage. That
authorization is deliberately scoped to **one** qualification frame and does not
authorize persistent TX, automatic retry, beaconing, connected mode, firmware
writes, GPIO/reset work, or option-byte changes.

## Product under test

The physically qualified installed appliance remains:

- installed product commit: `2f5299e65add072fea6ee55a54dc421faf00c276`
- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- firmware: exact AX25R4 identity
- artifact SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- frequency: 145.050 MHz
- qualified TX power byte: 200

The persistent appliance configuration must enter Stage I with TX disabled and
automatic flash disabled. Stage I does not edit `/etc/ywd-1278/config.toml`.

## Acceptance design

`tools/qualify_stage_i_single_tx.py` is a qualification harness, not a general
transmitter UI. Default invocation is dry-run and performs no service, UART,
KISS-TX, or RF action.

Physical mode requires both:

- command-line token `STAGE-I-TX-145050-ONE`
- interactive phrase `TRANSMIT-STAGE-I-ONE`

The harness then:

1. revalidates the Stage-F service-eligibility record and exact firmware artifact;
2. requires the normal Stage-H service to be enabled/active with persistent TX off;
3. stops the normal service and proves PTY/UART release;
4. rechecks the exact supported HAT target and AX25R4 identity;
5. derives a root-only temporary config in `/run/ywd-1278-stage-i/`;
6. changes only the temporary TX power/TX-enable and isolated KISS/console/PTY endpoints;
7. starts the **installed product daemon** with that temporary config;
8. injects exactly one localhost KISS DATA message, without FCS;
9. requires product diagnostics to show exactly one accepted request and one TX dispatch;
10. holds and rechecks diagnostics to prove no second internal dispatch;
11. requires operator confirmation that an independent receiver decoded the exact frame once;
12. requires a later non-qualification packet to arrive through KISS after the half-duplex TX/RX restart;
13. requires queue depth zero, subscriber drops zero, access timeouts zero, and downstream failures zero;
14. stops the temporary TX-capable daemon, removes the `/run` config, and restores the normal no-TX service;
15. rechecks that the persistent config remained unchanged and still has TX disabled.

## Fixed RF vector

Direct AX.25 UI frame, no digipeater path:

`KJ6YWD-10>YWD127:YWD-1278 STAGE-I TX 1/1`

The KISS DATA body excludes FCS; the TNC appends FCS through the already-qualified
product path. There is no application retry loop and no protocol requiring an
acknowledgement or retransmission.

## Required physical evidence

Stage I cannot be called qualified until all of the following are observed on the
real fresh-OS appliance:

- exactly one KISS DATA ingress;
- exactly one product TX dispatch;
- exactly one independently decoded matching RF frame;
- no second dispatch during the post-dispatch hold;
- a later packet received after TX/RX restart;
- final TX queue depth zero;
- zero subscriber drops;
- zero access timeouts;
- zero downstream failures;
- temporary TX runtime stopped;
- normal service restored enabled/active;
- persistent TX remains disabled;
- no firmware/option-byte write.

Until that evidence exists, Stage I remains host-staged / physical-TX-pending.
