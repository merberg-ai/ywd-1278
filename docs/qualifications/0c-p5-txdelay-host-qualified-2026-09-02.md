# 0C-P5 — TXDELAY host qualification

Date: 2026-09-02

Status: **host-qualified; physical YWDNOD follow-on pending**

Base: `checkpoint/0c-p4e-live-multicycle-qualified` at `b6b18631e9e1abaa2854f1a69a7a4dc56d08e71d`.

## Qualified behavior

YWD-1278 now has a bounded construction-time TXDELAY policy using KISS-style unsigned-byte semantics: `0..255`, 10 ms per count. Requested delay is conservatively rounded upward to complete 8-bit HDLC opening flags at 1200 baud. A zero request still emits one legal opening delimiter.

The continuity-critical default is exact: `TXDELAY=30` resolves to 300 ms and 45 flags, and the new `TXDelayBroker` reproduces the frozen P5 reference serializer exactly: 38 frame bytes, 691 selectors, 87 packed bytes, packed SHA256 `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`.

The historically qualified `TXBroker` was not modified. Its Git blob remains `1e3307dccea4f2805d32cb9be5b34f3537e29c4f`. `TXDelayBroker` subclasses that frozen queue/worker/preflight boundary and overrides only deterministic frame preparation.

No runtime TXDELAY setter is present. KISS parameter ingress, KISS DATA TX, product TX, POSIX serial, UART, RF, flash, GPIO/reset, and option-byte paths remain absent from this host gate.

## Host CI evidence

Staging head `0906a64d84bcdc45713f690ae6a641c7243c8c9a` passed:

- `p5-ci` run `33713270977` — SUCCESS
- `framework-ci` #393 / run `33713284950` — SUCCESS

The qualified boundary additionally folds `tests/txdelay_test.py` and `tests/txdelay_contract_test.py` into the permanent framework workflow.

## Physical follow-on locked to YWDNOD

Per operator requirement, all RF qualification packets in this phase must attempt to use the digipeater station KJ6YWD-5 through its AX.25 alias path `VIA YWDNOD`.

Two profiles are pre-locked:

1. 300 ms: `TXDELAY=30`, 45 opening flags, packet `KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 300MS 1/2`, 817 selectors, 13072 generated samples.
2. 500 ms: `TXDELAY=50`, 75 opening flags, packet `KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 500MS 2/2`, 1057 selectors, 16912 generated samples.

The physical qualification gate will require independent direct decoding and an attempted/observed digipeater repeat with the path consumed, conventionally displayed as `YWDNOD*`, while preserving the already-qualified P4e half-duplex lifecycle and channel-access safety.
