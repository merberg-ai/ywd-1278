# Qualified YWD-MMDVM -> YWD-1278 Porting Manifest

Source repository: `merberg-ai/ywd-mmdvm`

Frozen source boundary:

- branch/checkpoint: `checkpoint/ax25-bidirectional-tnc-foundation`
- evidence commit: `d25180ad663d781b761c525d1e699e7b052d6214`

The YWD-1278 product must port from this frozen boundary, not from whichever experimental branch happens to be newest later.

## Planned host-side imports

| Qualified source | YWD-1278 destination | Purpose | Port rule |
|---|---|---|---|
| `tools/ax25/ax25.py` | `src/ywd1278/ax25/codec.py` | AX.25 addresses, FCS, modulo-8 I/S/U parsing | **ported in 0B-P4** from source blob `d708f3b5f355c4a16bd917fd8b992d47f7008a1d`; preserve canonical CRC and frozen physical-capture vectors |
| `tools/ax25/ax25.py` KISS helpers + `tools/ax25/kiss_stream.py` | `src/ywd1278/kiss/framing.py` | KISS packet/stream framing | later phase; preserve escaping and stream resynchronization behavior |
| `tools/ax25/afsk1200.py` | `src/ywd1278/phy/bell202_tx.py` | HDLC/NRZI/Bell-202 TX selector generation | preserve physical selector equivalence |
| `tools/packetd/streaming_rx.py` | `src/ywd1278/phy/bell202_rx.py` | realtime 19.2ksps Bell-202 RX | preserve 144-hypothesis qualified bank and duty gate |
| `tools/packetd/ywd_packetd.py` | split into `kiss/server.py` + event model | TCP KISS and RX publication | remove lab naming; preserve frame semantics |
| `tools/packetd/tx_pipeline.py` | `src/ywd1278/phy/tx_pipeline.py` | KISS DATA -> qualified TX representation | preserve FCS/selector equivalence gate |
| `tools/packetd/tx_backend.py` | `src/ywd1278/service/tx_broker.py` | bounded TX request handoff | evolve only after CSMA design |
| `tools/packetd/bidirectional_runtime.py` | `src/ywd1278/modem/owner.py` | single UART owner RX/TX sequencing | preserve single-owner invariant |
| `tools/ax25/ax25_classic_test.py` protocol pieces | `src/ywd1278/modem/protocol.py` | MMDVM/YWD control protocol | productize without changing proven opcodes |
| `tools/ax25/ax25_rx3_capture.py` protocol pieces | `src/ywd1278/modem/protocol.py` | RX3 status/read protocol | preserve protocol revision checks |

## 0B-P4 AX.25 codec port

The first host-side port is intentionally narrow and hardware-independent.

Source implementation:

- `tools/ax25/ax25.py`
- source blob: `d708f3b5f355c4a16bd917fd8b992d47f7008a1d`

Source regression vectors:

- `tools/ax25/test_ax25.py`
- source blob: `47311cbe167a9d62195eb3987aefd4630569f86b`

YWD-1278 destination:

- `src/ywd1278/ax25/codec.py`
- `tests/ax25_codec_test.py`

P4 preserves:

- AX.25 shifted callsign/SSID encoding and decoding;
- CRC-16/X-25 / AX.25 FCS generation and verification;
- UI-frame construction;
- common one-octet-control modulo-8 I frame parsing;
- RR/RNR/REJ/SREJ supervisory parsing;
- UI/DM/SABM/DISC/UA/SABME/FRMR/XID/TEST unnumbered parsing;
- two FCS-valid physical AX25R3 capture vectors that were independently decoded by Direwolf.

P4 deliberately does **not** contain KISS stream logic, Bell-202 modulation/demodulation, UART ownership, GPIO access, or RF operations.

## Firmware lineage

The product firmware is rebuilt deterministically from the pinned upstream MMDVM_HS lineage rather than copying an opaque binary.

Relevant qualified engineering layers include:

- `firmware/ax25-classic1/` — Bell-202 TX engine;
- `firmware/ax25-rx1/` / `ax25-rx2/` / `ax25-rx3/` — passive slicer/RX layers and filtering;
- the final AX25R3 transformed tree used by the physical bidirectional qualification.

Product firmware work must:

1. retain upstream GPL/SPDX notices;
2. change user-visible YWD engineering identities to `YWD-1278` branding;
3. preserve proven internal host/modem protocol opcodes unless a real technical requirement demands a revision;
4. never write STM32 option bytes;
5. produce deterministic build artifacts and SHA256 values;
6. be tied to an explicit hardware target manifest entry;
7. pass RX, TX, KISS, lifecycle, and external decode regression gates before `flash_enabled` can become true for a target.

## Do not port

The new product should not copy the complete YWD-MMDVM lab menu, temporary capture files, one-off experiments, or historical qualification harnesses into runtime code.

Keep qualification tests when they protect an important invariant, but product code should be organized around stable modules rather than the chronological experiment sequence.

## First product requalification

The first YWD-1278 packet-engine milestone must prove, on unchanged qualified hardware:

- exact firmware/product identity;
- zero-drop realtime RX;
- standard TCP KISS RX;
- standard KISS-originated TX;
- one external independent Bell-202/AX.25 decode;
- return to RX after TX;
- bounded queue/UART ownership;
- no unexpected RF keyups;
- clean service stop/restart;
- no option-byte writes.

Only after that checkpoint should channel access, beaconing, or connected mode be layered on top.
