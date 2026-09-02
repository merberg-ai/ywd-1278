# 0B-P4 — AX.25 codec/FCS/parser qualification

Date: 2026-09-02

Status: **QUALIFIED**

## Scope

0B-P4 ports the proven host-side AX.25 codec primitives from the frozen YWD-MMDVM packet foundation into the YWD-1278 product package. This phase is intentionally limited to address handling, AX.25 FCS, UI-frame construction, and common modulo-8 I/S/U parsing.

KISS stream framing, Bell-202 serialization/demodulation, UART ownership, GPIO control, and RF operations are explicitly outside P4.

## Frozen source boundary

Source repository: `merberg-ai/ywd-mmdvm`

Frozen source checkpoint:

- branch: `checkpoint/ax25-bidirectional-tnc-foundation`
- evidence commit: `d25180ad663d781b761c525d1e699e7b052d6214`

Imported reference implementation:

- `tools/ax25/ax25.py`
- source blob: `d708f3b5f355c4a16bd917fd8b992d47f7008a1d`

Imported reference tests/vectors:

- `tools/ax25/test_ax25.py`
- source blob: `47311cbe167a9d62195eb3987aefd4630569f86b`

## YWD-1278 code boundary

Functional port boundary before qualification-document commits:

`db86a49ac00aa131e66790c8ade4168879e68ca9`

Product files:

- `src/ywd1278/ax25/__init__.py`
- `src/ywd1278/ax25/codec.py`
- `tests/ax25_codec_test.py`

CI workflow was extended with an `AX.25 codec regression` step.

## Preserved behavior

P4 preserves the frozen reference behavior for:

- callsign/SSID parsing and validation;
- seven-byte shifted AX.25 address encoding/decoding;
- C/H flag and address-extension handling;
- CRC-16/X-25 / AX.25 FCS generation;
- little-endian AX.25 FCS append/verification;
- modulo-8 UI frame construction;
- modulo-8 I frames with N(S), N(R), P/F, PID, and information field;
- supervisory RR/RNR/REJ/SREJ parsing;
- common unnumbered UI/DM/SABM/DISC/UA/SABME/FRMR/XID/TEST parsing.

## Deterministic regression evidence

### Canonical CRC vector

Input:

`123456789`

Expected CRC-16/X-25 check value:

`0x906E`

Result: **PASS**

### Frozen physical AX.25 capture #1

Bytes including FCS:

`a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 20 f0 6e 0d 00 28`

Previously independently decoded over the air by Direwolf as:

`KJ6YWD-1>RDG:n<CR>`

P4 assertions:

- FCS valid — PASS
- destination `RDG` — PASS
- source `KJ6YWD-1` — PASS
- frame class `I` — PASS
- control `0x20` — PASS
- N(S) = 0 — PASS
- N(R) = 1 — PASS
- PID = `0xF0` — PASS
- info = `n\r` — PASS

### Frozen physical AX.25 capture #2

Bytes including FCS:

`a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 82 f0 6d 68 0d 70 23`

Previously independently decoded by Direwolf as:

`KJ6YWD-1>RDG:mh<CR>`

P4 assertions:

- FCS valid — PASS
- frame class `I` — PASS
- control `0x82` — PASS
- N(S) = 1 — PASS
- N(R) = 4 — PASS
- PID = `0xF0` — PASS
- info = `mh\r` — PASS

Additional regression coverage includes UI round trip, callsign rejection cases, bad-FCS rejection, supervisory RR parsing, SABM parsing, UA with P/F parsing, and an FCS-less UI representation for the later KISS boundary.

## CI evidence

GitHub Actions run:

`33649532886`

The `validate` job completed successfully. Relevant successful steps include:

- Shell syntax
- Setup prompt regression
- Compile Python
- **AX.25 codec regression**
- Firmware identity classification
- Firmware build contract
- Firmware backup contract
- Firmware roundtrip contract
- Parse manifests and config
- Install package
- Framework self-test

The P4 test emits:

- `AX25_CODEC_PORT=PASS`
- `AX25_FCS_VECTOR=PASS`
- `AX25_PHYSICAL_CAPTURE_VECTORS=PASS`
- `AX25_MOD8_I_S_U_PARSER=PASS`
- `MODEM_UART_OPENED=NO`
- `RF_TRANSMITTED=NO`

## Safety / isolation

P4 is host-only protocol code.

- modem UART opened: **NO**
- GPIO accessed: **NO**
- RF configured: **NO**
- RF transmitted: **NO**
- STM32 flash written: **NO**
- option bytes written: **NO**
- product firmware flash gate remains closed.

## Result

**0B-P4 QUALIFIED.**

The AX.25 codec/FCS/common modulo-8 parser has been ported from the frozen proven source boundary and its important deterministic and previously physical-capture vectors pass in YWD-1278. The next isolated port gate is Bell-202 TX serialization; no RF transmission is required for that host-side equivalence step.
