# 0C-P4e live — persistent half-duplex multi-cycle physically qualified

Date: 2026-09-02

Status: **physically qualified**

Staged checkpoint: `checkpoint/0c-p4e-live-multicycle-staged-green` at `b19784a37f9500b14546a32410f6988be8a76c80`.

Host lifecycle checkpoint: `checkpoint/0c-p4e-persistent-half-duplex-host-qualified` at `0257f9947aea60d943b6b6b52e2ad7d9e28766de`.

## Result

The guarded P4e live harness completed three consecutive real half-duplex cycles on the AX25R4 MMDVM HAT at 145.050 MHz / RF power `200/255`:

`RX -> decoded inbound BUSY -> qualified CSMA -> RX_STOP -> fixed TX -> RF idle -> RX_START -> working RX again`

After the third TX and RX restart, the receive path independently decoded a fourth FCS-valid AX.25 frame while no TX request was queued. An independent receiver also decoded all three exact outgoing P4e qualification packets. Therefore the physical P4e promotion gate is satisfied.

## Live counters

- complete RX/TX/RX cycles: `3`
- initial RX starts: `1`
- post-TX RX restarts: `3`
- total RX starts: `4`
- TX submissions: `3`
- inbound FCS-valid frames: `4`
- fresh decoded pre-TX triggers: `3`
- final post-TX FCS-valid receive proof: **PASS**
- RSSI samples: `647`
- packed RX bytes drained: `100277`
- RX status checks: `157`
- peak FIFO available: `122` bytes
- FIFO dropped bytes: `0`
- one modem owner: **PASS**
- UART released: **YES**

## Per-cycle channel-access and lifecycle proof

Every cycle independently satisfied all of the following:

- a live RSSI BUSY observation occurred;
- a fresh FCS-valid inbound AX.25 packet was decoded after the previous RX start/restart;
- the first post-clear deterministic persistence trial used byte `255` and deferred;
- the next full slot used byte `0` and dispatched exactly once;
- `RX_STOP -> TX -> RF idle -> RX_START` completed;
- RX returned active after TX;
- FIFO drops remained zero.

The measured timing was identical on all three cycles:

- detector CLEAR to `255` defer: `0.150 s`
- defer to `0` dispatch: `0.100 s`

This is consistent with the qualified P1 100 ms slot timing and the P2 recent-RX/clear-release behavior.

## Fixed outgoing frames

1. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 1/3`
   - 40 frame bytes
   - 705 selectors
   - expected 11280 generated samples
2. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 2/3`
   - 40 frame bytes
   - 705 selectors
   - expected 11280 generated samples
3. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 3/3`
   - 40 frame bytes
   - 705 selectors
   - expected 11280 generated samples

The visible final cycle diagnostic reported `keyups:1 generated_samples:11280`, matching the fixed staging vector and the firmware's reset-on-accept diagnostic semantics.

## Independent outgoing RF decode proof

The operator supplied a screenshot from the independent receiver showing all three exact outgoing packets in order:

- `20:22:01` — `KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 1/3`
- `20:22:16` — `KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 2/3`
- `20:22:29` — `KJ6YWD-10>YWD4E: YWD-1278 P4E CYCLE 3/3`

No claim is made here about unrelated traffic visible in the same receiver display; only the three locked `YWD4E` frames are used as P4e external-decode evidence.

## Final receive-after-third-TX proof

After cycle 3 reported TX complete and RX restart active, the harness opened `FINAL_POST_TX_RX_WINDOW` with no TX request queued. It then decoded:

- source: `KJ6YWD`
- destination: `JIM`
- path: `KRDG,KBANN,KJOHN,KBULN,WOODY`
- frame type: `UI`
- frame bytes: `60`
- information: `hellooo`

That fourth FCS-valid decode proves the real receive path remained functional after the third TX/restart rather than merely returning an active status flag.

## Safety result

The successful run reported:

- duplicate dispatch: **NO**
- automatic TX retry: **NO**
- KISS TX connected: **NO**
- product TX enabled: **NO**
- flash written: **NO**
- GPIO accessed: **NO**
- option bytes written: **NO**
- RF transmitted: **YES, exactly three fixed qualification bursts**

P4e therefore qualifies the repeated physical half-duplex lifecycle only. It does **not** authorize unrestricted TX or KISS-originated TX.

## Promotion consequence

0C-P4e live is complete. The next work may build on a physically proven persistent RX/TX/RX lifecycle, but KISS-originated transmit must remain disconnected until its own bounded ingress and external-decode qualification are staged and passed.
