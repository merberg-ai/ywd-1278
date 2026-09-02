# 0B-P9 — RX-only assembled product runtime qualification — 2026-09-02

## Result

**PASS**

The assembled YWD-1278 RX-only product runtime was qualified on the target Raspberry Pi using the same saved physical AX25R3 slicer capture already used by the P6/P8 replay gates.

This qualification proves the integrated host path:

`single ModemOwner -> YWD_RX revision-3 FIFO -> streaming Bell-202 decoder -> AX.25 PacketEvent -> bounded RX backend -> TCP KISS server -> ordinary localhost KISS client`

The saved 24,009-byte physical capture impersonated the packet-capable firmware FIFO. The actual YWD-1278 owner/runtime/decoder/event/KISS threads ran normally. No real modem UART was opened and no RF path was reachable.

## Qualifying code boundary

- repository: `merberg-ai/ywd-1278`
- branch: `dev`
- code boundary before this evidence document: `84becd6d3de60559d787e3e1bec9d332b4217919`
- commit message: `add target-Pi assembled RX runtime replay qualification`
- CI run: `33656561799`
- CI conclusion: **success**

The green CI run included the assembled RX product runtime regression plus every earlier AX.25, Bell-202, modem protocol, single-owner, POSIX transport, KISS, firmware, installer, package and framework gate.

## Target-Pi replay evidence

Target host: `pi5-norm`

Capture:

`/home/ywd/mmdvm-lab/ywd-mmdvm/logs/ax25-rx3-raw-20260901-174007.bin`

Invocation:

```bash
python3 tools/qualify_rx_product_runtime_replay.py "$CAP" \
  --host 127.0.0.1 \
  --port 8001
```

Port 8001 was confirmed free before the run.

Observed safety boundary:

```text
Packed bytes        : 24009
KISS listen         : 127.0.0.1:8001
Required identity   : MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed
Transport           : injected capture-backed YWD_RX revision-3 fake
Real modem UART     : NOT OPENED
TX API              : ABSENT
RF transmit         : IMPOSSIBLE IN THIS PATH
```

Observed KISS delivery:

```text
KISS_RX[1]=PASS bytes=15
KISS_RX[2]=PASS bytes=18
KISS_RX[3]=PASS bytes=19
```

Observed complete runtime result:

```text
PACKED_BYTES_CONSUMED=24009
YWD_RX_READ_TRANSACTIONS=122
YWD_RX_STATUS_CHECKS=19
DECODED_FRAMES=3
MODEM_OWNER_TRANSACTIONS=144
KISS_TX_REJECTED=1
KISS_SUBSCRIBER_DROPS=0
YWD1278_RX_PRODUCT_REPLAY=PASS frames=3
SINGLE_MODEM_OWNER=PASS
YWD_RX_FIFO_TO_BELL202=PASS
AX25_EVENT_TO_TCP_KISS=PASS
PACKET_FIRMWARE_IDENTITY_GATE=PASS
FIFO_DROPPED_BYTES=0
MODEM_UART_OPENED=NO
RF_CONFIGURED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

## Qualified properties

0B-P9 qualifies:

- exactly one typed modem-owner boundary for the assembled receive runtime;
- YWD_RX revision-3 START/READ/STATUS/STOP lifecycle through that owner;
- streaming Bell-202 consumption of the complete saved physical capture;
- exact recovery of the same three physical AX.25 packet occurrences;
- publication of decoded AX.25 events to the bounded KISS backend;
- byte-exact delivery of all three events through a real localhost TCP KISS client;
- explicit rejection of inbound KISS DATA while TX remains absent;
- zero KISS subscriber drops in the qualification run;
- zero reported RX FIFO dropped bytes;
- fail-closed firmware identity gate for the future packet-capable YWD-1278 AX25R3 image;
- no real modem UART access in this replay gate;
- no RF configuration or RF transmission;
- no flash or option-byte writes.

## Fail-closed runtime rules

The assembled RX runtime treats a nonzero firmware RX FIFO dropped-byte count as a fatal health error rather than silently continuing with a lossy stream. Packet firmware identity must match the expected YWD-1278 AX25R3 identity before receive operation is accepted.

## Not qualified by this gate

0B-P9 does **not** qualify:

- the packet-capable AX25R3 firmware build itself;
- live YWD_RX FIFO operation over `/dev/ttyAMA0`;
- live RF receive through the assembled runtime;
- any transmit-capable owner/runtime API;
- KISS-originated physical TX;
- CSMA/channel access;
- persistent systemd packet-service lifecycle.

Those remain separate later gates.
