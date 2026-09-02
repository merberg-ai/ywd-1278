# RX-only product runtime

## Scope

This stage assembles the already-qualified receive-side layers into the first product-shaped packet runtime while deliberately keeping TX disconnected.

Data path:

`single ModemOwner -> YWD_RX revision-3 FIFO -> StreamingBell202Decoder -> AX.25 PacketEvent -> RXOnlyBackend -> TCP KISS`

Implementation:

- `src/ywd1278/modem/owner.py` — sole transport owner and typed YWD_RX requests
- `src/ywd1278/service/rx_runtime.py` — receive lifecycle, decoder feed, health/fail-closed behavior
- `src/ywd1278/phy/bell202_rx.py` — qualified one-pass 144-hypothesis decoder
- `src/ywd1278/kiss/server.py` — bounded RX event history/subscriber queues and TCP KISS publication

## Safety and ownership invariants

The runtime does not import or open a serial device directly. Only `ModemOwner` receives a transport factory; the actual transport is created, used and closed in the owner thread.

There is no TX method in `RXOnlyPacketRuntime`. The RX-only KISS backend has no modem reference or transmit callback. Inbound KISS DATA remains counted/rejected rather than forwarded toward RF.

An exact expected packet-firmware identity is mandatory at startup. Stock MMDVM_HS firmware or any other identity therefore fails before `YWD_RX/START` is accepted as a valid product runtime.

## Startup

1. start the single modem owner;
2. GET_VERSION;
3. require exact packet-firmware identity;
4. issue `YWD_RX/START`;
5. read revision-3 status;
6. require active RX flags `0x0D`;
7. require zero FIFO drops;
8. start the receive worker.

## Receive loop

The worker may only call typed owner methods. It repeatedly reads at most 200 packed slicer bytes from the YWD_RX FIFO and feeds each byte exactly once to `StreamingBell202Decoder`.

Fresh FCS-valid AX.25 occurrences are converted to `PacketEvent` objects with the HDLC FCS removed, then published to `RXOnlyBackend`. Any attached TCP KISS server emits standard port-0 DATA frames.

Periodic revision-3 status checks require:

- flags remain `0x0D`;
- FIFO dropped-byte counter remains exactly zero.

Any reported FIFO drop is fatal. The runtime does not silently advertise a lossy receive stream as healthy.

## Shutdown

Normal stop:

1. stop the receive worker;
2. issue `YWD_RX/STOP` so firmware stops producing new samples;
3. drain the finite remaining FIFO tail through the same decoder;
4. finish the decoder (which has no DSP backlog by P6 design);
5. require armed-idle flags `0x04`;
6. require FIFO available bytes = 0;
7. require FIFO dropped bytes = 0;
8. stop the modem owner and release the transport.

Worker failure attempts a best-effort RX stop and owner shutdown so a failed receive service does not intentionally leave the UART session active.

## Current qualification boundary

The first regression uses a fake revision-3 modem transport plus the three frozen physical AX25R3 frame vectors. Synthetic Bell-202 slicer samples are returned through real YWD_RX protocol responses, processed by the product decoder, and received through a real localhost TCP KISS socket.

The regression also proves:

- exactly one modem owner;
- inbound KISS DATA is still rejected;
- subscriber queue drops remain zero in the nominal test;
- a non-zero FIFO dropped-byte status fails closed;
- no raw client UART API exists;
- no RF transmission occurs.

Live UART/YWD_RX and live RF receive are separate later gates and require a packet-capable YWD-1278 firmware image first.
