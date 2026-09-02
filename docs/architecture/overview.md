# YWD-1278 Architecture

## Product model

YWD-1278 is a Raspberry Pi packet TNC/node built around a compatible MMDVM_HS-style HAT. It intentionally keeps protocol/session intelligence on Linux and uses the HAT firmware as a bounded RF/physical-layer engine.

```text
KISS clients ─┐
TNC console ──┤
Beacon engine ┤
AX.25 links ──┤
Node/BBS ─────┤
              ▼
       RX event / TX broker
              │
      AX.25 + channel access
              │
       Bell-202 DSP/encoding
              │
       SINGLE UART OWNER
              │
             UART
              │
      STM32 + ADF7021 HAT
              │
              RF
```

## Non-negotiable ownership rule

Exactly one process/thread boundary owns the physical modem UART. Network clients, Telnet sessions, KISS handling, beacon timers, connected-mode sessions, database logging, and future WebUI code must never open the UART independently.

This rule comes directly from the qualified `ywd-mmdvm` packet service work and is preserved as a product invariant.

## Receive split

### HAT firmware

The HAT performs:

- RF receive and ADF7021 demodulator configuration;
- packet-specific receive filtering;
- 19.2 ksample/s one-bit slicer capture;
- bounded FIFO buffering;
- sample/drop counters;
- UART delivery to the Pi.

The STM32 does **not** implement AX.25 callsigns, FCS checking, connected sessions, KISS, or logging.

### Raspberry Pi

The Pi performs:

- Bell-202 MARK/SPACE classification;
- NRZI decode;
- HDLC flag detection;
- bit unstuffing;
- CRC/FCS verification;
- AX.25 frame parsing;
- occurrence deduplication;
- monitor/logging/event publication.

## Transmit split

### Raspberry Pi

The Pi constructs AX.25 and converts it through:

```text
AX.25 bytes
  -> FCS
  -> HDLC flags / bit stuffing
  -> NRZI
  -> Bell-202 tone selectors
```

### HAT firmware

The STM32 receives a bounded packed selector burst. Each 1200-baud selector is expanded to sixteen 19.2 ksample/s one-bit samples. The ADF7021 2FSK path converts that generated waveform into RF whose ordinary FM demodulated audio is interoperable Bell-202.

## Product services

Planned front doors:

- raw TCP KISS;
- virtual serial/PTY KISS;
- classic TNC-style command console;
- Telnet command console;
- later WebUI/API.

All front doors share the same packet engine and RX event stream.

## Safety boundaries

- bounded RX buffering;
- bounded TX queues;
- no unattended TX until CSMA/channel-access qualification;
- TX disabled by default in initial configuration;
- firmware writes only to allowlisted targets;
- protected pre-flash backup where supported/required;
- no STM32 option-byte writes;
- explicit firmware hash verification;
- restore-stock accepts only backups identified as stock for the exact target;
- service restart loops remain bounded by systemd start limits.
