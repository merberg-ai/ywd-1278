# 0C-P2 AX25R4 live raw-RSSI telemetry physical qualification — 2026-09-02

## Result

The exact staged AX25R4 RSSI firmware was successfully activated on the first supported physical target after the earlier R1 preflight false-negative was corrected. The exact P13b-qualified AX25R3 programmed bytes were verified before the write, the exact AX25R4 programmed bytes were verified after the write, the exact AX25R4 runtime identity answered after restart, and a bounded 20-second receive-only raw-RSSI observation completed with zero RX FIFO drops and zero RF TX activity.

This qualifies the **physical raw-RSSI telemetry path only**. It does not yet qualify a carrier threshold, hysteresis, busy/clear classifier, or CSMA integration.

## Exact target and firmware

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- device: `/dev/ttyAMA0`
- receive frequency: `145050000` Hz
- AX25R3 preflight SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- AX25R4 artifact bytes: `59892`
- AX25R4 artifact SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- programmed AX25R4 readback SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- runtime identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- AX25R4 intentionally left installed after the successful run

## Receive-only telemetry evidence

The live tool polled `YWD_RX/0x05` every 50 ms while continuously draining the bounded raw RX FIFO.

- observation duration: `20.0 s`
- RSSI samples: `401`
- raw minimum: `47`
- raw p05: `48`
- raw median: `105`
- raw p95: `116`
- raw maximum: `122`
- distinct raw values: `32`
- packed bytes drained: `48021`
- read transactions: `2444`
- RSSI transactions: `401`
- status checks: `42`
- firmware sample counter: `20 -> 384173`
- peak FIFO available: `10` bytes
- FIFO dropped bytes: `0`
- owner transactions: `2896`
- single modem owner: PASS
- UART released: YES

## Observed RSSI structure

A post-run analysis of all 401 samples found three coherent low-value events:

- `3.301–4.052 s`
- `6.152–6.850 s`
- `10.400–11.152 s`

Using `90` only as an analysis cut—not a production threshold—produces two completely separated observed populations:

- low/event cluster: 47 samples, range `47..73`, median `48`
- normal cluster: 354 samples, range `95..122`, median `106`
- no observed samples in the integer range `74..94`

This strongly suggests that **lower raw magnitude corresponds to stronger received RF** on this target. The three events were not independently labeled during this observation, however, so this evidence alone must not choose the production carrier threshold or hysteresis.

## TX and recovery safety evidence

- RF keyups: `0 -> 0`
- RF TX generated samples: `0 -> 0`
- TX command path in live probe: ABSENT
- ordinary KISS TX: DISCONNECTED
- persistent product TX: DISABLED
- RF transmitted: NO
- option bytes written: NO
- carrier threshold selected: NO
- hysteresis selected: NO

The earlier R1 activation false-negative remains documented separately. It failed before any candidate write because `stm32flash` informational stdout contaminated command-substitution output. R2 corrected only that process-boundary issue and then completed the guarded activation successfully.

## Boundary after this qualification

The physical firmware installed on the target is now the exact AX25R4 image above. The **0C-P2 channel-busy detector is still incomplete** until RSSI polarity, threshold margin, and hysteresis/recent-RX behavior are deliberately characterized and locked. KISS-originated TX remains disconnected throughout that work.
