# 0C-P4e live — guarded persistent half-duplex multi-cycle staging

Date: 2026-09-02

Status: **staged; not yet physically run**

Base: `checkpoint/0c-p4e-persistent-half-duplex-host-qualified` at `0257f9947aea60d943b6b6b52e2ad7d9e28766de`.

## Question this gate answers

P4d-R2 proved one real CSMA-controlled RX-to-TX handoff. P4e host qualification proved the reusable lifecycle over a fake thread-bound modem transport. This live gate asks the remaining physical question before any external TX ingress is considered:

**Can the real AX25R4 HAT repeatedly return to a genuinely working receive path after each transmitted packet?**

The proof requires actual FCS-valid decoded packets after RX restarts, not only firmware status flags.

## Fixed physical profile

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- firmware: exact already-installed qualified AX25R4 identity
- frequency: `145.050 MHz`
- RF power: `200/255`
- outgoing TX count: exactly three maximum
- automatic retry: none
- KISS/product TX: disconnected
- firmware flash/GPIO/reset/option-byte access: absent

No CLI argument can change frequency, power, device, frame payload, cycle count, or retry behavior.

## Fixed outgoing frames

1. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 1/3`
   - 40 frame bytes
   - 705 selectors / 89 packed bytes
   - packed SHA256 `6aac46f53fb71633e7b103aa97644eecd68e3c1a07c437e594c018e1b1700b03`
   - 11280 generated samples
2. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 2/3`
   - 40 frame bytes
   - 705 selectors / 89 packed bytes
   - packed SHA256 `c162c20d54180885d8b842b6922e4afb157dd1dec4fb514d378a39ba7f1e65a4`
   - 11280 generated samples
3. `KJ6YWD-10>YWD4E:YWD-1278 P4E CYCLE 3/3`
   - 40 frame bytes
   - 705 selectors / 89 packed bytes
   - packed SHA256 `715b21aadabc4b4fbb019c5cd44a333fe754d7a099d53a70955842dc14e92f65`
   - 11280 generated samples

Independent over-air decoding must later confirm all three exact outgoing frames before promotion.

## Per-cycle receive/access/TX proof

For each cycle the harness creates a fresh streaming Bell-202 decoder after the previous RX restart and queues only that cycle's fixed outgoing frame.

The request remains forced to persistence byte `255` until **both** conditions have happened during that cycle:

1. live RSSI drove the qualified detector to BUSY; and
2. the HAT's receive stream independently produced a fresh FCS-valid AX.25 decode.

Only then does the deterministic qualification sequence permit `255` after one complete P1 slot and `0` after a second complete slot. At READY, the already host-qualified `PersistentHalfDuplexSubmitter` performs:

`RX_STOP -> one TXBroker submission -> RF idle proof -> RX_START -> active RX proof`

Every cycle requires zero FIFO drops, one reset-on-accept completed keyup, and exactly 11280 generated samples.

## Final receive-only proof

After cycle 3 completes, the access queue must be empty. The harness constructs a fresh Bell-202 decoder and opens a receive-only window with **no TX request queued**. It must decode another fresh FCS-valid AX.25 packet after the third RX restart.

Therefore a successful run has at least four inbound FCS-valid decodes:

- one trigger before TX cycle 1;
- one after the cycle-1 restart / before TX cycle 2;
- one after the cycle-2 restart / before TX cycle 3;
- one after the cycle-3 restart with no TX request queued.

## Failure/rerun safety

The harness derives accepted-TX count from both the P4e lifecycle snapshot and the concrete broker snapshot. If any failure occurs after one or more TX submissions were accepted, it prints `DO_NOT_RERUN_FULL_P4E_LIVE_HARNESS=YES`. A post-TX RX-restart failure therefore cannot be mislabeled as a safe zero-TX failure.

No automatic frame retry exists in the lifecycle, access queue, or qualification harness.

## Promotion rule

Do not mark physical P4e complete until all of the following exist together:

- live harness PASS;
- three complete RX/TX/RX cycles;
- zero FIFO drops;
- three fresh pre-TX inbound FCS-valid decodes;
- one final post-TX inbound FCS-valid decode;
- exact independent receiver decode of all three outgoing fixed packets;
- one modem owner and clean UART release;
- no duplicate dispatch or automatic retry;
- KISS/product TX still disconnected.
