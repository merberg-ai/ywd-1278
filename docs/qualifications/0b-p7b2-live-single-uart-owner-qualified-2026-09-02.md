# 0B-P7b-2 — Live single-UART owner qualification — 2026-09-02

Status: **QUALIFIED**

## Scope

This gate physically qualifies the YWD-1278 single-owner modem runtime against the first supported Raspberry Pi 5 + MMDVM_HS HAT target using the real modem UART.

The qualification is intentionally read-only and minimal. It opens `/dev/ttyAMA0` through the private POSIX transport from the dedicated `ModemOwner` thread, sends exactly one MMDVM `GET_VERSION` request, validates the response against the target manifest, closes the transport from the same owner thread, and verifies that the UART is free afterward.

No GPIO operation, RX session, RF configuration, TX command, flash operation, or option-byte operation is part of this gate.

## Hardware / target

- Host: Raspberry Pi 5 Model B Rev 1.0 (`pi5-norm`)
- Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- Running firmware at qualification time: stock MMDVM_HS
- Exact returned identity: `MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed`
- Protocol version: `1`

## Precondition evidence

Before the live owner probe:

- `/dev/ttyAMA0` was free;
- `ywd-1278.service` was `disabled`;
- `ywd-1278.service` was `inactive`.

## Live qualification command

```bash
sudo python3 tools/qualify_modem_owner_identity.py \
  --target mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021 \
  --device /dev/ttyAMA0
```

## Physical result

The qualification reported:

```text
YWD1278_MODEM_OWNER_IDENTITY=PASS
MODEM_UART_OPENED=YES
MODEM_TRANSACTIONS=1
MODEM_SINGLE_OWNER=YES
MODEM_COMMANDS_SENT=GET_VERSION_ONLY
RF_CONFIGURED=NO
RX_STARTED=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

Observed response:

```text
Protocol version : 1
Identity         : MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed
Transactions     : 1
```

After the qualification process exited, `/dev/ttyAMA0` was confirmed free again.

## Qualified invariants

This physical gate confirms:

1. the real POSIX serial transport can open `/dev/ttyAMA0` at the required MMDVM host settings;
2. the transport is constructed and used inside the dedicated owner thread;
3. exactly one modem transaction was issued;
4. that transaction was exactly MMDVM `GET_VERSION` (`E0 03 00`);
5. the returned stock identity is decoded correctly through the P7a protocol codec;
6. transport shutdown releases the UART cleanly;
7. no modem TX API is exposed by the qualified owner boundary;
8. no RF was configured or transmitted;
9. no STM32 flash or option-byte operation occurred.

## Boundary

The implementation under qualification is the `dev` tree containing the POSIX transport fix at:

`36feaa06b3d524c7a3b63f5aecdc522f14b1c56e`

The final frozen checkpoint may include this evidence/roadmap documentation on top of that code boundary.

## Out of scope

This gate does **not** qualify:

- live RX session ownership (`YWD_RX/START`, `READ`, `STATUS`, `STOP`);
- Bell-202 decoding from a live UART stream;
- KISS TCP service;
- any TX path;
- packet-capable YWD-1278 firmware deployment.

Those remain subsequent explicit qualification gates.
