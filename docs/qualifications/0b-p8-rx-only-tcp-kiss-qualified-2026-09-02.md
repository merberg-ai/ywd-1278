# 0B-P8 — RX-only TCP KISS qualification — 2026-09-02

## Result

**PASS**

The YWD-1278 host-side TCP KISS boundary was qualified on the target Raspberry Pi using the same saved physical AX25R3 slicer capture already used by 0B-P6.

This qualification proves the path:

`saved physical slicer capture -> qualified streaming Bell-202 decoder -> AX.25 packet events -> RX-only bounded event backend -> TCP KISS server -> ordinary localhost KISS client`

It deliberately does **not** open the modem UART, configure RF, start live modem receive, expose a TX callback, transmit RF, write STM32 flash, or write option bytes.

## Qualifying code boundary

- repository: `merberg-ai/ywd-1278`
- branch: `dev`
- code boundary before this evidence document: `8b16c907b2cffe30a2400adf8a672168c78f088f`
- commit message: `add target-Pi RX-only KISS replay qualification`
- CI run: `33655005082`
- CI conclusion: **success**

The green CI run included:

- KISS framing regression: PASS
- RX-only TCP KISS server regression: PASS
- POSIX modem transport regression: PASS
- single-owner modem regression: PASS
- all earlier AX.25, Bell-202, firmware, installer, package and framework gates: PASS

## Relevant implementation

- `src/ywd1278/kiss/framing.py`
- `src/ywd1278/kiss/server.py`
- `tools/qualify_kiss_replay.py`
- `tests/kiss_framing_test.py`
- `tests/kiss_server_test.py`

The server uses bounded per-client queues. Client KISS DATA is counted and rejected by the RX-only backend. There is no modem-owner reference or transmit callback in this layer.

## Physical-source replay evidence

Target host: `pi5-norm`

Capture:

`/home/ywd/mmdvm-lab/ywd-mmdvm/logs/ax25-rx3-raw-20260901-174007.bin`

Invocation:

```bash
python3 tools/qualify_kiss_replay.py "$CAP" \
  --host 127.0.0.1 \
  --port 8001
```

Port 8001 was confirmed free before the run.

Observed decoded events:

1. `KJ6YWD-1>RDG type=SABM` — 15 AX.25 bytes without FCS
2. `KJ6YWD-1>RDG type=I` — 18 AX.25 bytes without FCS
3. `KJ6YWD-1>RDG type=I` — 19 AX.25 bytes without FCS

Observed TCP KISS client results:

```text
KISS_RX[1]=PASS bytes=15
KISS_RX[2]=PASS bytes=18
KISS_RX[3]=PASS bytes=19
KISS_TX_REJECTED=1
KISS_SUBSCRIBER_DROPS=0
YWD1278_KISS_REPLAY=PASS frames=3
KISS_TCP_SERVER=PASS
KISS_STANDARD_DATA_PORT0=PASS
KISS_CLIENT_TX_PATH=REJECTED
MODEM_UART_OPENED=NO
RF_CONFIGURED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

The client deliberately sent one standard KISS DATA frame back to the server. That frame was accounted as rejected exactly once and was not handed toward any modem or RF path.

## Qualified properties

0B-P8 qualifies:

- standard KISS `FEND`/`FESC` escaping and incremental stream resynchronization;
- standard KISS DATA command on port 0 for received AX.25 frames;
- real TCP socket delivery on `127.0.0.1:8001`;
- byte-exact delivery of all three saved physically sourced AX.25 occurrences;
- bounded per-client RX queues;
- zero subscriber drops in the qualification run;
- explicit rejection of inbound client KISS DATA while TX remains absent;
- no modem UART access in this path;
- no RF configuration or RF transmission;
- no flash or option-byte writes.

## Not qualified by this gate

0B-P8 does **not** qualify:

- live `YWD_RX` FIFO operation;
- live RF receive through YWD-1278 packet-capable firmware;
- any KISS-originated transmit path;
- CSMA/channel access;
- persistent daemon/service lifecycle;
- external over-air TX decode.

Those remain separate later gates.
