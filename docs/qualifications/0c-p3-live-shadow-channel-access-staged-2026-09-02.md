# 0C-P3 live shadow channel-access integration — staged 2026-09-02

## Status

**STAGED / CI-PENDING — physical receive-only qualification not yet run.**

0C-P3 composes the already-qualified 0C-P2 RSSI busy detector with the already-qualified 0C-P1 p-persistent CSMA policy while deliberately keeping all transmit paths disconnected. The physical qualification will run against the exact AX25R4 firmware already installed on the first supported HAT; no firmware write or reset is part of this phase.

## Frozen prerequisites

- current project checkpoint: `checkpoint/0c-p2-channel-busy-detector-qualified`
- checkpoint SHA: `ddd881b868f851cf955703e1e7d277d1537b76d9`
- installed AX25R4 artifact: 59892 bytes
- installed AX25R4 SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- installed identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- live receive frequency: 145.050 MHz

0C-P2 remains unchanged: lower raw RSSI is physically qualified as stronger RF; busy asserts at raw `<=83`, clear release requires raw `>=90`, `84..89` is hysteresis, and 250 ms continuously on the clear-release side is required before the detector reports CLEAR.

0C-P1 remains unchanged: `PERSIST=63` (25%), `SLOTTIME=10` (100 ms), 30 s bounded access wait, explicit caller-supplied time/randomness, any busy observation cancels an in-progress clear slot, and only a later explicit clear observation begins a new full slot.

## Host integration staged

`src/ywd1278/tx/channel_access.py` adds a pure `ShadowChannelAccessAttempt`:

1. one caller-supplied raw RSSI observation advances `RSSIChannelBusyDetector`;
2. the detector's `channel_busy` boolean is passed unchanged into `PersistentCSMA.observe()`;
3. caller-supplied randomness is requested only when the detector is CLEAR and a P1 persistence slot is actually due;
4. no hidden clock, sleep, RNG, modem, UART, network, KISS, broker, or TX operation exists in the bridge;
5. READY is observational only and inherits P1's existing single-use terminal semantics.

`src/ywd1278/service/live_channel_access.py` adds a synchronous `LiveChannelAccessSampler`. It attaches to an already-running RX-only `ModemOwner`, preflights active loss-free packet RX, performs exactly one typed `owner.rx_rssi()` transaction per sample, and feeds the result to the pure shadow attempt. It does not start/stop/reconfigure RX and contains no thread, hidden timing loop, RNG, TX owner, broker, or KISS connection.

The existing `RXOnlyPacketRuntime` is deliberately not rewritten. 0C-P3 is a sidecar sharing the same single modem owner.

## Staged physical proof

The one-purpose tool `tools/qualify_live_shadow_channel_access.py` is fixed to:

- `/dev/ttyAMA0`
- 145.050 MHz RX
- exact AX25R4 identity above
- 20 s maximum observation window
- 50 ms RSSI polling
- minimum one FCS-valid AX.25 frame during the live window

The qualification persistence source is explicit and deterministic rather than hidden RNG:

- before the first real live BUSY observation: byte `255`, keeping the shadow attempt non-terminal;
- first persistence trial after BUSY -> RECENT_RX -> CLEAR -> full 100 ms P1 slot: byte `255`, which must defer;
- second post-busy persistence trial after another full 100 ms clear slot: byte `0`, which must reach READY.

The physical run must prove all of the following in the same bounded receive-only session:

- a real FCS-valid AX.25 frame is decoded;
- the qualified RSSI detector observes BUSY;
- BUSY forces P1 to `WAIT_CLEAR` and cancels any prior slot;
- detector `RECENT_RX` remains busy-for-access;
- detector CLEAR after the 250 ms hold starts a new full P1 100 ms slot;
- post-busy byte `255` defers one persistence trial;
- post-busy byte `0` reaches shadow READY on the following full slot;
- RX FIFO drops remain zero;
- RF keyups do not change;
- RF generated-TX sample count does not change;
- exactly one base `ModemOwner` owns the UART.

## Safety boundary

0C-P3 does **not** connect READY to anything capable of transmitting. `TXModemOwner`, `TXBroker`, ordinary KISS TX, daemon TX, and persistent product TX remain disconnected. The physical tool performs no flash, GPIO/reset, option-byte operation, or RF transmit command. The AX25R4 firmware already installed by 0C-P2 remains untouched.

The next promotion gate is host CI followed by the bounded live receive-only shadow qualification above. Only after that proof can a later phase consider connecting a queued TX request to this channel-access result, and that later work still must preserve the bounded broker and KISS safety gates.
