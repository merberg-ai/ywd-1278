# 0B-P12b Live RF-to-TCP-KISS Qualification — 2026-09-02

Status: **PHYSICALLY QUALIFIED**

This qualification proves the complete YWD-1278 receive-only packet path on the real Raspberry Pi 5 + MMDVM_HS HAT using a new live over-air Bell-202 AX.25 packet on the local 145.050 MHz packet-network frequency:

`live RF -> ADF7021 / STM32 AX25R3 -> YWD_RX FIFO -> single ModemOwner -> streaming Bell-202 -> AX.25 event -> RX-only backend -> TCP KISS port 0`

P12b deliberately did **not** qualify any YWD transmit path. Inbound TCP KISS DATA was injected once and had to be rejected. No flash, GPIO/reset, modem TX command, RF keyup, generated TX samples, RF transmission, or option-byte write was permitted or observed.

## Prerequisite boundary

P12b started from the frozen 0B-P12a state:

- target status before the physical run: `0b-p12a-live-rx-qualified`
- exact AX25R3 packet firmware already installed on the HAT
- normal product `flash_enabled=false`
- P3 qualification write gate closed
- P11 packet qualification write gate closed
- P12a activation/write gate closed
- option-byte writes forbidden
- modem UART released

P12a historical receive evidence remains exactly **144.390 MHz** (`144390000` Hz). P12b used its own independent staging field at **145.050 MHz** (`145050000` Hz). P12a evidence was not rewritten or repurposed.

## Hardware / target

- Host: Raspberry Pi 5
- Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- MCU: STM32F103 medium density
- ADF7021 RF TCXO: 14.7456 MHz
- STM32 HSE: 8 MHz
- P12b receive frequency: `145050000` Hz
- TCP KISS listener: `127.0.0.1:8001`
- qualification wait limit: 120 seconds
- minimum required live frames: 1

## Packet firmware identity

The running firmware identity gate passed with the exact P10/P11/P12a-qualified packet firmware:

`MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Artifact:

`firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Exact artifact properties remain:

- bytes: `59812`
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- frozen engineering source: `d25180ad663d781b761c525d1e699e7b052d6214`

P12b performed **no firmware write** and **no reset**.

## Exact live packet proof

One new live AX.25 UI frame was received over RF, decoded by the assembled runtime, delivered to the ordinary TCP KISS client on port 0, and parsed successfully.

Observed frame:

- source: `KJ6YWD`
- destination: `JIM`
- digipeater path: `KRDG,KBANN,KJOHN,KBULN,WOODY`
- frame type: `UI`
- PID: `0xF0`
- information: `test test`
- AX.25 frame bytes delivered through KISS: `60`

Exact delivered AX.25 frame hex:

`94929a404040e096946cb2ae886096a4888e4040609684829c9c406096949e909c40609684aa989c4060ae9e9e88b2406103f0746573742074657374`

Qualification output:

```text
LIVE_KISS[1] source=KJ6YWD destination=JIM type=UI bytes=60
LIVE_KISS_HEX[1]=94929a404040e096946cb2ae886096a4888e4040609684829c9c406096949e909c40609684aa989c4060ae9e9e88b2406103f0746573742074657374
```

## Live runtime counters

Observed end-to-end counters:

- decoded frames: `1`
- live KISS frames: `1`
- packed RX bytes: `27101`
- YWD_RX read transactions: `2511`
- YWD_RX status checks: `24`
- firmware samples: `216815`
- FIFO dropped bytes: `0`
- modem owner transactions: `2543`
- KISS subscriber drops: `0`
- rejected inbound KISS DATA requests: `1`

The complete live path therefore reached TCP KISS without FIFO loss or subscriber-queue loss.

## Single-owner / TCP KISS safety proof

The physical test used the assembled `RXOnlyPacketRuntime` and one `ModemOwner` over `/dev/ttyAMA0`.

The KISS listener was loopback-only at `127.0.0.1:8001`.

Before waiting for the live RF packet, the client deliberately sent one inbound KISS DATA frame containing:

`P12B CLIENT TX MUST REMAIN DISCONNECTED`

The RX-only backend rejected it exactly once:

- `KISS_TX_REJECTED=1`
- `KISS_CLIENT_TX_PATH=REJECTED`

There was no TX broker or modem transmit dependency behind the KISS backend.

After the live receive qualification completed:

- single modem owner: **PASS**
- owner stopped cleanly: **YES**
- UART released: **YES**
- KISS subscriber drops: `0`

## Explicit RF / write safety observations

RF diagnostics before and after the physical test were unchanged:

- RF keyups: `0 -> 0`
- RF TX generated samples: `0 -> 0`
- RF transmitted: **NO**

The qualification also reported:

- `FLASH_WRITTEN=NO`
- `GPIO_ACCESSED=NO`
- `TX_COMMAND_PATH=ABSENT`
- `RF_TRANSMITTED=NO`
- `OPTION_BYTES_WRITTEN=NO`

No STM32 main-flash operation, bootloader operation, GPIO reset/BOOT0 manipulation, packet TX command, or option-byte write occurred in P12b.

## Pass markers

The physical run produced all required pass markers:

```text
YWD1278_0B_P12B_LIVE_RF_KISS=PASS
P12A_PACKET_FIRMWARE_IDENTITY_GATE=PASS
SINGLE_MODEM_OWNER=PASS
LIVE_YWD_RX_FIFO=PASS
LIVE_BELL202_DECODE=PASS
LIVE_AX25_EVENT=PASS
LIVE_TCP_KISS_PORT0=PASS
KISS_CLIENT_TX_PATH=REJECTED
FIFO_DROPPED_BYTES=0
KISS_SUBSCRIBER_DROPS=0
MODEM_UART_RELEASED=YES
FLASH_WRITTEN=NO
GPIO_ACCESSED=NO
TX_COMMAND_PATH=ABSENT
RF_TRANSMITTED=NO
OPTION_BYTES_WRITTEN=NO
```

## Qualification boundary

0B-P12b closes the receive-only live packet-engine proof. The complete product receive path is now physically proven on 145.050 MHz from real RF through ordinary TCP KISS with bounded queues, exactly one UART owner, zero observed receive loss, and no transmit activity.

P12b does **not** qualify bidirectional KISS or unrestricted packet transmission.

The next TX work must remain deliberately bounded:

1. add a bounded TX broker above the existing single modem owner;
2. add only a typed owner TX method behind that broker;
3. reuse the already-qualified 0B-P5 Bell-202 serializer rather than redoing waveform work;
4. keep inbound TCP KISS DATA disconnected initially;
5. perform one guarded known-packet YWD transmit on 145.050 MHz;
6. verify that packet with an independent external decoder/receiver;
7. only after that proof, connect KISS-originated TX through the bounded broker and later CSMA policy.

Until those later gates pass, YWD-1278 TX remains unqualified through the product runtime.
