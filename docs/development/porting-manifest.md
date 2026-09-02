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
| `tools/ax25/afsk1200.py` | `src/ywd1278/phy/bell202_tx.py` | HDLC/NRZI/Bell-202 TX selector generation | **ported in 0B-P5** from source blob `c3aecf7a8f22ef0f051177873482538dddbd6828`; preserve exact AX25-5B selector count and packed-selector representation |
| `tools/packetd/streaming_rx.py` | `src/ywd1278/phy/bell202_rx.py` | realtime 19.2ksps Bell-202 RX | **ported in 0B-P6** from source blob `5f31d97a264557ca985e028b50dcbdeda05672ab`; preserve 144-hypothesis bank, exact physical-frame replay, and realtime duty gate |
| `tools/packetd/ywd_packetd.py` | split into `kiss/server.py` + event model | TCP KISS and RX publication | remove lab naming; preserve frame semantics |
| `tools/packetd/tx_pipeline.py` | `src/ywd1278/phy/tx_pipeline.py` | KISS DATA -> qualified TX representation | preserve FCS/selector equivalence gate |
| `tools/packetd/tx_backend.py` | `src/ywd1278/service/tx_broker.py` | bounded TX request handoff | evolve only after CSMA design |
| `tools/packetd/bidirectional_runtime.py` | `src/ywd1278/modem/owner.py` | single UART owner RX/TX sequencing | **ownership architecture ported in 0B-P7b-1** from source blob `e05750c18ccf5224e8cf082dfb3ad203b9d52f4b`; preserve single-owner invariant; TX sequencing remains later |
| `tools/ax25/ax25_classic_test.py` protocol pieces | `src/ywd1278/modem/protocol.py` | MMDVM/YWD control/RF protocol | **ported in 0B-P7a** from source blob `9e3ec6b431a7324d8ae5cbb7901156e33c62fd4b`; preserve qualified opcodes and frame layouts |
| `tools/ax25/ax25_rx_capture.py` + `ax25_rx3_capture.py` protocol pieces | `src/ywd1278/modem/protocol.py` | RX3 start/read/stop/status protocol | **ported in 0B-P7a** from blobs `115473e0ea741210aa074f955fbb69cc87d6a416` and `29d064b8b0d2be84eef749dc06d7a7d12309d0bc`; preserve revision-3 checks and FIFO counters |

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

## 0B-P5 Bell-202 TX serialization port

Source implementation:

- `tools/ax25/afsk1200.py`
- source blob: `c3aecf7a8f22ef0f051177873482538dddbd6828`

Source regression tests:

- `tools/ax25/test_afsk1200.py`
- source blob: `7ddd18cf00349ac73c93a2bf49f254607b8dceb0`

YWD-1278 destination:

- `src/ywd1278/phy/bell202_tx.py`
- `tests/bell202_tx_test.py`

P5 preserves:

- LSB-first HDLC byte serialization;
- flag `0x7E` representation;
- AX.25 five-one bit stuffing and inverse reference path;
- AX.25 NRZI (`0` changes tone, `1` holds tone);
- Bell-202 selector semantics: `0 = 1200 Hz MARK`, `1 = 2200 Hz SPACE`;
- MSB-first packed-selector UART representation;
- default 45 opening flags = exactly 300 ms at 1200 baud;
- default three closing flags.

A bit-exact regression is anchored to the previously physically-qualified AX25-5B transmission:

`KJ6YWD-10>APYWD1: AX25-5B KISS TX TEST`

The frozen physical qualification reported exactly **691 selectors** and `691 * 16 = 11056` generated STM32 samples, followed by an independent ordinary Bell-202/AX.25 decode of the exact packet. The P5 host-only regression requires the same 691-selector representation and locks its MSB-first packed-selector SHA256 to:

`30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e`

This P5 gate does not open the modem UART, expand samples, key RF, or issue a modem TX command. Physical YWD-1278 transmission remains a later requalification step.

## 0B-P6 realtime streaming Bell-202 RX port

Source implementation:

- `tools/packetd/streaming_rx.py`
- source blob: `5f31d97a264557ca985e028b50dcbdeda05672ab`

Relevant frozen source qualifications:

- `docs/qualifications/ax25-3c-streaming-realtime-qualified-2026-09-01.md`
- source qualification blob: `cfd73f6c3b3ce9de2778ff852c0336bcf4b000c5`

YWD-1278 destination:

- `src/ywd1278/phy/bell202_rx.py`
- `tests/bell202_rx_test.py`
- `tools/qualify_bell202_rx_replay.py`

P6 preserves:

- 19.2 ksps one-bit slicer input semantics;
- exact 12-sample Bell-202 correlation metric represented by a 4096-entry lookup table;
- persistent 1196..1204 baud x 16-phase acquisition coverage;
- exactly 144 persistent timing hypotheses;
- heap-scheduled symbol decisions rather than per-sample full-bank scanning;
- persistent NRZI and streaming HDLC state across arbitrary feed boundaries;
- AX.25 FCS plus structural frame validation;
- physical-occurrence dedupe without collapsing identical packets heard at separate times;
- no queued DSP drain at `finish()`.

The productized decoder passed the same saved 10.004-second physical AX25R3 capture at exactly 1.00x source rate on the target Raspberry Pi. It recovered the exact three frozen physical frame vectors at sample starts `998`, `56008`, and `154432`, with **52.5% processing duty**, **47.5% measured headroom**, zero late chunks, `0.0001 s` schedule slip, and `0.000002 s` post-stream drain.

P6 is host-side replay qualification only. The replay harness explicitly reports `MODEM_UART_OPENED=NO` and `RF_TRANSMITTED=NO`. Live UART ownership and live RF receive remain later gates.

## 0B-P7a modem wire protocol port

Source protocol pieces:

- `tools/ax25/ax25_classic_test.py` — blob `9e3ec6b431a7324d8ae5cbb7901156e33c62fd4b`
- `tools/ax25/ax25_rx_capture.py` — blob `115473e0ea741210aa074f955fbb69cc87d6a416`
- `tools/ax25/ax25_rx3_capture.py` — blob `29d064b8b0d2be84eef749dc06d7a7d12309d0bc`
- `tools/packetd/bidirectional_runtime.py` framing use — blob `e05750c18ccf5224e8cf082dfb3ad203b9d52f4b`

YWD-1278 destination:

- `src/ywd1278/modem/protocol.py`
- `src/ywd1278/modem/__init__.py`
- `tests/modem_protocol_test.py`

P7a preserves the proven MMDVM/YWD byte protocol, including `YWD_CONTROL=0x56`, `YWD_DATA=0x57`, `YWD_RF=0x58`, `YWD_RX=0x59`, RF status/diagnostic/TX/abort/exit subcommands, RX start/read/stop/status subcommands, and RX protocol revision 3.

The codec validates the start byte and exact declared frame length, enforces expected command responses, validates ACK/NAK payloads, rejects malformed RX reads and wrong RX protocol revisions, and keeps all serialization pure and deterministic.

A regression reconnects P7a to the physically-qualified AX25-5B path without transmitting: the P5 packet `KJ6YWD-10>APYWD1: AX25-5B KISS TX TEST` still produces 691 selectors, which serialize into the expected 93-byte `YWD_RF/TX_TONES` host request with the packed selector payload unchanged.

P7a contains no serial transport and opens no device. UART ownership is intentionally deferred to P7b so the byte protocol can remain frozen underneath it.

## 0B-P7b-1 bounded single-owner runtime

Source architectural reference:

- `tools/packetd/bidirectional_runtime.py` — blob `e05750c18ccf5224e8cf082dfb3ad203b9d52f4b`

YWD-1278 destination:

- `src/ywd1278/modem/owner.py`
- `tests/modem_owner_test.py`

P7b-1 turns the earlier single-owner convention into a structural API boundary. The transport factory runs inside one dedicated owner thread, and the transport instance is created, used, and closed there. Callers cannot submit raw MMDVM frames; the public surface contains typed GET_VERSION, RX start/read/status/stop, and read-only RF-diagnostic calls only.

A bounded `queue.Queue` mediates client requests. The regression deliberately blocks the owner inside a fake transaction, fills a one-entry queue, and requires the next request to fail closed with `ModemOwnerQueueFull`. The fake transport also binds to its construction thread and rejects direct calls from the test/client thread.

There is intentionally no owner API for `YWD_RF/TX_TONES`, arbitrary raw transact, RF abort, or RF exit at this gate. TX ownership will be added only after its bounded broker and lifecycle sequencing are separately qualified.

P7b-1 is device-free. A thread-bound POSIX serial transport and guarded live read-only GET_VERSION proof are P7b-2. Live YWD_RX remains deferred until a packet-capable YWD-1278 firmware image is built and qualified.

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
