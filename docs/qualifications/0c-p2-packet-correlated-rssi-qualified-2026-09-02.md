# 0C-P2 packet-correlated RSSI physical qualification — 2026-09-02

## Result

The exact already-installed AX25R4 firmware was observed receive-only on `145.050 MHz` until two distinct FCS-valid AX.25 frame events were decoded by the previously qualified streaming Bell-202 receiver. Raw ADF7021 RSSI measurements taken inside those decoded frame intervals were then compared against an independent population of RSSI measurements outside ±0.5 seconds of the decoded frames.

The result is a strong physical proof that **lower raw ADF7021 register-7 magnitude corresponds to stronger received RF on this target**. Both decoded packet windows had median raw RSSI `48`, while the independent outside-frame population had median `106`, yielding a `58`-count polarity margin against the staged minimum requirement of `12` counts.

This qualification also records a physically observed empty guard region between the signal/transition population and the upper population, but it still does **not** enable a production carrier threshold, hysteresis, busy/clear decision, CSMA integration, KISS TX, or product TX. Those policy choices remain an explicit host-only gate after this evidence is frozen.

## Exact physical boundary

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- device: `/dev/ttyAMA0`
- receive frequency: `145050000` Hz
- firmware bytes: `59892`
- firmware SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- previously verified programmed readback SHA256: same exact SHA
- runtime identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- firmware was already installed before this run and remained installed afterward
- no firmware flash occurred during this run

## Two independently decoded packet events

The streaming Bell-202 receiver already suppresses duplicate timing-hypothesis detections for the same physical occurrence. The qualification therefore required two distinct valid frame occurrences, not two decoder hypotheses finding one packet.

### Frame 1

- decoder sample interval: `99924..108636`
- bytes including FCS: `68`
- frame hex: `94929a404040e096946cb2ae886096a4888e4040609684829c9c406096949e909c40609684aa989c4060ae9e9e88b2406103f037332066726f6d2072656464696e677b48`
- AX.25: `KJ6YWD>JIM` via `KRDG,KBANN,KJOHN,KBULN,WOODY`
- control/PID: UI / `0xF0`
- information: `73 from redding`
- correlated RSSI samples: `9`
- raw RSSI: min `47`, median `48`, max `48`

### Frame 2

- decoder sample interval: `149339..157403`
- bytes including FCS: `63`
- frame hex: `94929a404040e096946cb2ae886096a4888e4040609684829c9c406096949e909c40609684aa989c4060ae9e9e88b2406103f068656c6c6f20746573744509`
- AX.25: `KJ6YWD>JIM` via `KRDG,KBANN,KJOHN,KBULN,WOODY`
- control/PID: UI / `0xF0`
- information: `hello test`
- correlated RSSI samples: `9`
- raw RSSI: min `47`, median `48`, max `48`

## Independent polarity proof

The polarity test was intentionally made independent of guard-gap selection so it could not prove its own assumption circularly.

- RSSI samples collected: `301`
- decoded valid AX.25 frames: `2`
- correlated frame windows: `2`
- exclusion around each decoded frame for the comparison population: ±`0.5 s`
- outside-frame RSSI samples remaining: `243`
- worst packet-window median raw RSSI: `48`
- outside-frame median raw RSSI: `106`
- required polarity margin: `12` raw counts
- observed polarity margin: `58` raw counts
- result: PASS
- proven polarity: **lower raw magnitude = stronger received RF**

## Observed guard-gap structure

Only after the polarity proof passed was the packet-referenced guard gap characterized.

- packet signal reference maximum: `48`
- observed signal/transition side: `47..70`, median `48`
- observed upper population: `97..121`, median `106`
- observed empty guard gap: `70..97`
- gap width: `27` raw counts
- descriptive midpoint: `83`

The midpoint `83` is evidence, not an enabled production threshold. No classifier behavior is changed by this qualification.

## Runtime and safety evidence

- packed RX bytes drained: `36070`
- YWD_RX read transactions: `596`
- RSSI transactions: `301`
- status checks: `32`
- peak FIFO available: `67` bytes
- FIFO dropped bytes: `0`
- modem-owner transactions: `938`
- single modem owner: PASS
- UART released: YES
- RF keyups: `0 -> 0`
- RF TX generated samples: `0 -> 0`
- TX command path in qualification tool: ABSENT
- KISS TX connected: NO
- product TX enabled: NO
- RF transmitted: NO
- firmware flashed: NO
- GPIO accessed: NO
- option bytes written: NO
- CSMA integrated: NO

## Boundary after this qualification

The physical measurement source and its polarity are now qualified strongly enough to ground a deterministic host-side busy/recent-RX classifier. The first telemetry capture remains frozen separately and is not rewritten by this later evidence.

The next gate is therefore host-only: choose conservative assert/release thresholds from the physically empty guard region, define recent-RX hold behavior, exhaustively test threshold/hysteresis transitions, and keep that classifier disconnected from the modem/CSMA/TX runtime until its own contract is green.
