# 0C-P2 channel-busy/recent-RX detector host qualification — 2026-09-02

## Result

0C-P2 now has both halves needed before runtime integration can begin:

1. **physical measurement qualification** — exact AX25R4 firmware on the target correlated two distinct FCS-valid AX.25 packet intervals with raw ADF7021 RSSI and independently proved that lower raw magnitude means stronger received RF; and
2. **host-only detector qualification** — a deterministic, fail-closed hysteretic state machine converts explicit raw RSSI observations into UNKNOWN / BUSY / RECENT_RX / CLEAR without importing or reaching the modem, UART, KISS, CSMA, TX broker, GPIO, or firmware tooling.

This does **not** yet integrate the detector with the live modem owner or the already-qualified 0C-P1 p-persistent CSMA policy. It does not connect KISS-originated TX. No RF transmission is authorized by this qualification.

## Frozen physical evidence anchor

Immutable checkpoint:

`checkpoint/0c-p2-rssi-packet-correlation-qualified`

at exact commit:

`3a81fcdf8825af1267ce03af255c5f02c2242ba6`

The physical run used the exact installed AX25R4 image:

- firmware bytes: `59892`
- SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- receive frequency: `145050000` Hz

Two distinct FCS-valid packet occurrences were correlated:

- `KJ6YWD>JIM` via `KRDG,KBANN,KJOHN,KBULN,WOODY`, information `73 from redding`, packet-window RSSI median `48`
- `KJ6YWD>JIM` via the same path, information `hello test`, packet-window RSSI median `48`

Independent outside-frame evidence:

- outside-frame samples: `243`
- packet worst median: `48`
- outside-frame median: `106`
- required polarity margin: `12`
- observed polarity margin: `58`
- proven polarity: **lower raw magnitude = stronger RF**

Observed physical guard structure:

- signal/transition side: `47..70`, median `48`
- upper population: `97..121`, median `106`
- physically empty region: `70..97`
- descriptive midpoint: `83`

The physical run itself selected no carrier threshold or hysteresis. Those values are introduced only by the host policy below.

## Qualified host policy

Module:

`src/ywd1278/tx/channel_busy.py`

Locked policy values:

- busy assert: raw `<= 83`
- clear release eligibility: raw `>= 90`
- hysteresis band: raw `84..89`
- recent-RX / continuous-clear hold: `0.250 s`
- physical RSSI polling period used to ground the hold: `0.050 s`
- hold therefore spans five physical polling periods

The two thresholds both sit inside the physically empty `70..97` region:

- observed busy/transition maximum `70` -> busy assert `83`: `13` raw counts of margin
- clear release `90` -> observed upper-population minimum `97`: `7` raw counts of margin

## State semantics

The detector starts `UNKNOWN` and fails closed for channel access. Only `CLEAR` maps to `channel_busy=False`.

- `raw <= 83`: assert `BUSY` immediately; cancel any pending clear qualification
- `raw 84..89`: true hysteresis band
  - when already CLEAR, remain CLEAR until the assert threshold is crossed
  - from UNKNOWN/BUSY/RECENT_RX, remain non-clear and cancel pending release qualification
- `raw >= 90` from a non-clear state: enter/continue `RECENT_RX` clear qualification
- continuously `raw >= 90` for a full `0.250 s`: become `CLEAR`
- a new busy observation immediately returns to BUSY and restarts clear history
- caller time must be monotonic; invalid raw values fail as programmer errors

This intentionally avoids crediting unobserved time or ambiguous hysteresis-band values as clear-channel evidence.

## Relationship to 0C-P1

The existing 0C-P1 p-persistent policy remains unchanged:

- `PERSIST=63`
- `SLOTTIME=10` = `100 ms`
- `30 s` bounded wait
- first explicit clear observation starts a full clear slot
- busy cancels/reset slot timing

0C-P2 is **not yet connected to 0C-P1**. When integration is deliberately staged later, the detector's 250 ms continuous clear qualification will occur before P1 can receive a clear observation; P1 then still requires its own full 100 ms clear slot before a persistence trial. No part of this host qualification bypasses those existing P1 semantics.

## CI qualification

PR staging CI run `framework-ci #321` completed successfully on the corrected detector staging head after one contract-only false failure was fixed. The original behavior regression passed even in the false-failure run; the failed architecture check had forbidden the generic English substring `random` and matched the module docstring phrase `draw random numbers`. The contract was narrowed to forbid actual RNG imports/calls (`import random`, `from random`, `random.`) without changing detector behavior.

Green gates include:

- deterministic channel-busy detector regression
- channel-busy architecture/evidence contract
- deterministic 0C-P1 CSMA regression and architecture contract
- RSSI telemetry / firmware / activation / packet-correlation contracts
- all frozen P13b qualification contracts
- POSIX transport, KISS, RX runtime, firmware, install, and framework self-test gates

## Safety boundary

- modem/UART integration: NO
- live RSSI polling integration: NO
- CSMA integration: NO
- TX broker integration: NO
- KISS-originated TX: DISCONNECTED
- persistent product TX: DISABLED
- RF transmission performed by host-policy qualification: NO
- firmware write: NO
- GPIO/reset access: NO
- option-byte writes: NO

## Next gate

The next step is an explicit integration qualification that feeds live/read-only RSSI observations into this detector and then feeds only the resulting boolean busy/clear observation into the unchanged 0C-P1 state machine. That integration must remain TX-disconnected first. Only after the combined detector + CSMA path is host/live-RX qualified should any KISS-originated frame be allowed to reach the bounded TX broker.
