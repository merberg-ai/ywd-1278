# 0B-P7a Modem Wire Protocol Port Qualification — 2026-09-02

Status: **QUALIFIED — pure host protocol codec**

## Qualification boundary

- repository: `merberg-ai/ywd-1278`
- branch under qualification: `dev`
- qualifying code boundary: `ba27bdea34c721c3acc00def8b4f908a46381531`
- CI workflow run: `33652110973` — **SUCCESS**
- frozen source repository: `merberg-ai/ywd-mmdvm`
- frozen source checkpoint: `d25180ad663d781b761c525d1e699e7b052d6214`

P7a deliberately qualifies only the deterministic YWD/MMDVM wire format. It contains no serial-port open, no UART ownership, no GPIO operation, no modem configuration, and no RF operation.

## Source lineage

Qualified source protocol pieces were taken from:

- `tools/ax25/ax25_classic_test.py` — source blob `9e3ec6b431a7324d8ae5cbb7901156e33c62fd4b`
- `tools/ax25/ax25_rx_capture.py` — source blob `115473e0ea741210aa074f955fbb69cc87d6a416`
- `tools/ax25/ax25_rx3_capture.py` — source blob `29d064b8b0d2be84eef749dc06d7a7d12309d0bc`
- `tools/packetd/bidirectional_runtime.py` — source blob `e05750c18ccf5224e8cf082dfb3ad203b9d52f4b`

YWD-1278 destination:

- `src/ywd1278/modem/protocol.py`
- `src/ywd1278/modem/__init__.py`
- `tests/modem_protocol_test.py`

## Preserved protocol constants

The port intentionally preserves the proven internal opcodes rather than renaming them for product branding:

```text
START        = 0xE0
GET_VERSION  = 0x00
SET_CONFIG   = 0x02
SET_FREQ     = 0x04
ACK          = 0x70
NAK          = 0x7F
YWD_CONTROL  = 0x56
YWD_DATA     = 0x57
YWD_RF       = 0x58
YWD_RX       = 0x59

RF_GET_STATUS = 0x01
RF_TX_TONES   = 0x02
RF_ABORT      = 0x03
RF_EXIT       = 0x04
RF_GET_DIAG   = 0x05

RX_START      = 0x01
RX_READ       = 0x02
RX_STOP       = 0x03
RX_STATUS     = 0x04
RX protocol revision = 3
```

This follows the product porting rule that user-visible branding may change while already-qualified internal host/modem protocol opcodes remain stable unless a real technical requirement demands a revision.

## Bit-exact request gates

CI locks the qualified request bytes:

```text
GET_VERSION       e0 03 00
CONTROL/PING      e0 04 56 01
RF/GET_STATUS     e0 04 58 01
RF/GET_DIAG       e0 04 58 05
RX/START          e0 04 59 01
RX/STATUS         e0 04 59 04
RX/READ 200       e0 05 59 02 c8
ACK for YWD_RX    e0 04 70 59
```

The parser fails closed on invalid start bytes, truncated frames, declared/actual length mismatches, unexpected command responses, malformed ACK/NAK payloads, wrong RX protocol revisions, and RX read byte-count mismatches.

## AX25-5B TX representation gate

P7a does **not** transmit. It only proves that the wire serializer still represents the frozen physically-qualified AX25-5B request correctly.

Frozen packet:

```text
KJ6YWD-10>APYWD1: AX25-5B KISS TX TEST
```

The already-qualified P5 serializer produces exactly `691` Bell-202 selectors. P7a packs those selectors into the preserved `YWD_RF/TX_TONES` request and requires:

- selector count: `691`
- packed selector bytes: `87`
- total MMDVM host request bytes: `93`
- command: `YWD_RF (0x58)`
- subcommand: `RF_TX_TONES (0x02)`
- selector count encoded little-endian in the two qualified count bytes
- packed selector payload byte-for-byte identical to the P5 representation

This connects the P5 bitstream equivalence boundary to the future modem-owner layer without opening a UART.

## RX3 response layout gate

P7a preserves the revision-3 receive status layout:

- protocol revision
- RX flags
- available packed FIFO bytes
- 32-bit generated slicer sample counter
- 16-bit dropped packed-byte counter

The test vector verifies revision `3`, active flags `0x0d`, 120 available bytes, 192061 generated samples, and zero dropped bytes. Wrong protocol revisions are rejected.

## CI result

GitHub Actions run `33652110973` completed successfully. The `Modem protocol regression` step passed together with all existing AX.25, Bell-202 RX/TX, installer, firmware build, backup, roundtrip, and framework safety regressions.

## Safety properties

- modem UART opened: **NO**
- serial transport present in P7a: **NO**
- RF configured: **NO**
- RF transmitted: **NO**
- firmware written: **NO**
- STM32 option bytes written: **NO**
- normal product flash gate changed: **NO**

## Qualification conclusion

**0B-P7a is QUALIFIED.**

The YWD-1278 product now has a deterministic, fail-closed codec for the already-qualified YWD/MMDVM AX.25 host protocol. The next gate, 0B-P7b, may build the single-UART-owner transport/runtime on top of this frozen byte boundary without duplicating or reinterpreting protocol framing in higher layers.
