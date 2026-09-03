# 0C-P7 live KISS one-shot — physically qualified

Date: 2026-09-03

Base host checkpoint: `checkpoint/0c-p7-kiss-data-admission-host-qualified` -> `3df9a46f0851876e55c078ab41504584304bef38`

Frozen staged checkpoint: `checkpoint/0c-p7-live-kiss-one-shot-staged-green` -> `788702f5b66999c3ba1e69f29b23f8c7eae28484`

## Result

The guarded physical P7 harness completed successfully on the already-installed AX25R4 firmware at 145.050 MHz and RF power 200/255.

One localhost KISS DATA message was admitted on port 0 without FCS. The TNC appended the AX.25 FCS exactly once, preserved parameter generation 3 (`TXDELAY=30`, `PERSIST=63`, `SLOTTIME=10`), and closed the localhost KISS listener before channel-access dispatch.

A fresh non-P7 FCS-valid inbound packet plus live BUSY were required before transmission. Channel access then produced the fixed deterministic qualification sequence: `255` persistence defer after 150 ms, followed by `0` dispatch 100 ms later. The P4e half-duplex lifecycle completed `RX_STOP -> TX -> RF idle -> RX_START` successfully.

The single transmitted frame was the locked 52-byte FCS-bearing vector corresponding to:

`KJ6YWD-10>YWD7,YWDNOD:YWD-1278 P7 KISS VERIFY 1/1`

It produced 801 selectors, 101 packed selector bytes, packed-selector SHA256 `82fff4f7b03ae787fb16d6d14cc9a59e81e7b3f751a3e4be1e090320d26b2b7f`, one completed keyup, and 12816 generated samples.

After RX restart, the Pi first decoded its own P7 qualification frame and correctly ignored it as recovery proof. It then decoded a separate FCS-valid `KJ6YWD-5>KE6CHO-5` RR frame, proving real receive operation after the KISS-originated TX.

## Physical counters

- KISS DATA messages received: 1
- KISS DATA admitted: 1
- TX submissions: 1
- inbound FCS-valid frames: 3
- qualifying non-P7 inbound frames: 2
- qualification echoes ignored: 1
- RSSI samples: 188
- packed RX bytes drained: 86271
- RX status checks: 137
- peak FIFO available: 130 bytes
- FIFO dropped bytes: 0
- clear -> defer: 0.150 s
- defer -> dispatch: 0.100 s
- completed-burst keyups: 1
- completed-burst generated samples: 12816

## Independent receiver proof

The operator-supplied independent AXConsole receiver screenshot shows the exact direct decode at local time 14:21:18:

`KJ6YWD-10 > YWD7 via YWDNOD`

`YWD-1278 P7 KISS VERIFY 1/1`

This satisfies the P7 direct external-decode gate. The separate `YWDNOD*` repeat proof remains deferred and non-blocking.

## Safety result

- single modem owner: PASS
- UART released: YES
- duplicate dispatch: NO
- automatic TX retry: NO
- persistent KISS TX enabled: NO
- product TX enabled: NO
- flash written: NO
- GPIO accessed: NO
- option bytes written: NO
- RF transmitted: exactly one KISS-originated burst

P7 is physically qualified. Persistent product KISS TX remains disabled; the next boundary is sustained bounded KISS TNC operation (0C-P8).
