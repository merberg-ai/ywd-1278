# 0B-P5 — Bell-202 TX serialization qualification

Date: 2026-09-02

Status: **QUALIFIED**

## Scope

0B-P5 ports the proven host-side AX.25 HDLC / Bell-202 TX serializer from the frozen YWD-MMDVM packet foundation into YWD-1278. This phase stops at the one-selector-per-1200-baud-symbol representation used by the already-qualified modem transport.

P5 does not open the modem UART, issue a modem TX command, expand selectors into STM32 samples, configure RF, or key the transmitter.

## Frozen source boundary

Source repository: `merberg-ai/ywd-mmdvm`

Frozen checkpoint:

- `checkpoint/ax25-bidirectional-tnc-foundation`
- evidence commit `d25180ad663d781b761c525d1e699e7b052d6214`

Reference implementation:

- `tools/ax25/afsk1200.py`
- blob `c3aecf7a8f22ef0f051177873482538dddbd6828`

Reference tests:

- `tools/ax25/test_afsk1200.py`
- blob `7ddd18cf00349ac73c93a2bf49f254607b8dceb0`

## YWD-1278 functional boundary

Functional P5 boundary before qualification-document commits:

`fa4207d60849258a790aaf7ccb15346a2ab0625b`

Product files:

- `src/ywd1278/phy/__init__.py`
- `src/ywd1278/phy/bell202_tx.py`
- `tests/bell202_tx_test.py`

CI includes a dedicated `Bell-202 TX serialization regression` step.

## Preserved representation

P5 preserves:

- AX.25 bytes serialized LSB first;
- HDLC flag byte `0x7E` as LSB-first bits `0 1 1 1 1 1 1 0`;
- insertion of a zero after five consecutive one bits in frame data;
- reference bit-unstuffing path with malformed-stuffing rejection;
- AX.25 NRZI semantics: zero changes state, one holds state;
- Bell-202 selector semantics:
  - `0` = MARK / 1200 Hz
  - `1` = SPACE / 2200 Hz;
- initial MARK state;
- packed selector representation MSB first;
- default 45 opening flags, equal to exactly 300 ms at 1200 baud;
- default three closing flags.

## Physical-qualification equivalence anchor

The frozen AX25-5B physical qualification transmitted this exact ordinary KISS-originated AX.25 UI packet:

`KJ6YWD-10>APYWD1: AX25-5B KISS TX TEST`

That prior physical qualification recorded:

- Bell-202 selectors: `691`
- nominal duration: `691 / 1200 = 0.575833... s`
- STM32 samples per selector: `16`
- observed expected sample delta: `691 * 16 = 11056`
- exact packet independently decoded over RF by an ordinary packet receiver.

The YWD-1278 P4+P5 host pipeline reconstructs the FCS-bearing frame as:

`82a0b2ae8862e096946cb2ae887503f0415832352d3542204b4953532054582054455354f8ff`

P5 then requires exactly:

- selector count: `691`
- packed selector bytes: `87`
- packed selector SHA256:
  `30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

This freezes the bit-level host serialization representation that fed the previously interoperable physical transmission.

## Additional regression evidence

The P5 test also verifies:

- HDLC flag bit order;
- bit-stuff / unstuff round trip;
- invalid stuffing rejection;
- NRZI encode / decode round trip;
- selector packing / unpacking round trip;
- real AX.25 frame HDLC pre/post flags and body recovery;
- 45-flag default TX delay behavior.

The test emits:

- `BELL202_TX_SERIALIZER_PORT=PASS`
- `HDLC_BIT_STUFFING=PASS`
- `AX25_NRZI=PASS`
- `SELECTOR_PACKING=PASS`
- `AX25_5B_SELECTOR_COUNT=691`
- `AX25_5B_SELECTOR_PACKED_SHA256=30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`
- `MODEM_UART_OPENED=NO`
- `RF_TRANSMITTED=NO`

## CI evidence

GitHub Actions run:

`33650137529`

The complete `validate` job finished successfully. The dedicated Bell-202 TX serialization regression passed along with the AX.25 codec, all firmware safety/round-trip contracts, package installation, and framework self-test.

## Safety / qualification boundary

- modem UART opened: **NO**
- modem TX command issued: **NO**
- GPIO accessed: **NO**
- RF configured: **NO**
- RF transmitted: **NO**
- STM32 flash written: **NO**
- option bytes written: **NO**
- normal firmware `flash_enabled` remains **false**.

The previously demonstrated YWD-MMDVM over-air interoperability is used only as a fixed equivalence anchor. P5 does **not** claim that YWD-1278 has yet requalified physical transmission; that remains a later combined runtime/RF gate.

## Result

**0B-P5 QUALIFIED.**

The proven HDLC bit ordering, stuffing, NRZI, and Bell-202 selector representation is now present in YWD-1278 with a bit-exact regression tied to the prior physical AX25-5B transmission. The next isolated host-side port is the realtime streaming Bell-202 receiver.
