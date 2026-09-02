# 0B-P13b-R2 Corrected Three-Packet Verification Staging — 2026-09-02

Status: **STAGED / HOST-QUALIFIED — PHYSICAL R2 RF NOT YET EXECUTED**

P13b-R2 is the corrected external-decode verification sequence after the R1 physical attempt exposed a host-side diagnostic-accounting mistake.

## Why R2 exists

R1 submitted its first fixed burst and then raised `expected one RF keyup ... observed delta=0` before bursts 2 and 3.

The frozen firmware source explains the false-negative: `CAX25AFSKTX::writeSelectors()` resets `m_keyups` and `m_samplesQueued` to zero whenever a new burst is accepted. Diagnostics therefore represent the current/most recently accepted burst, not lifetime cumulative TX counters across multiple bursts.

R2 validates each completed burst using the firmware's real semantics:

- completed burst `keyups == 1`;
- completed burst `generated_samples == selector_count * 16`;
- `remaining_selectors == 0` and `tx_active == 0` after each burst;
- diagnostics remain unchanged during the 5.0 s gap before the next submission;
- no cumulative multi-burst keyup/sample delta is invented.

## RF power correction

The original P13b one-shot and R1 retry used the RX-only setup helper's minimum nonzero RF power byte `1/255`.

The frozen YWD-MMDVM AX25-5B qualification that independently decoded the exact Bell-202 RF path on 145.050 MHz used **RF power `200/255`**.

R2 reuses exactly that already independently qualified RF level.

A new qualification-only typed operation on `TXModemOwner` applies one fixed profile:

- RX frequency: `145.050 MHz`;
- TX frequency: `145.050 MHz`;
- RF power: `200/255`.

The caller cannot supply a frequency or power argument. The frozen RX-only `ModemOwner` remains unchanged and ordinary product/KISS TX remains disconnected.

## Fixed R2 packet sequence

All three packets use:

- source: `KJ6YWD-10`
- destination: `YWD13B`
- UI / PID `0xF0`
- opening flags: `45`
- closing flags: `3`
- initial tone: `MARK`
- five-second pause between completed bursts

### Packet 1/3

`KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 1/3`

- frame bytes: `45`
- frame SHA256: `3d255111c073a51d9369e8fc26aaa6d9a9e8882cf532e0e56246913aaf5ece50`
- selectors: `745`
- packed selector bytes: `94`
- packed SHA256: `d147b12a8a24147c18f6a50847f866396e1d3d0ecd3595aeaecf7d99d22b7813`
- expected generated samples: `11920`

### Packet 2/3

`KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 2/3`

- frame bytes: `45`
- frame SHA256: `0a4064718049ac9b36d7e617805cc47daae11199fad08faa7f3621660104c678`
- selectors: `745`
- packed selector bytes: `94`
- packed SHA256: `14dd8eaf62ac46cc49acc81d55299912c909db9dc54f77b26df795f95aaa64ad`
- expected generated samples: `11920`

### Packet 3/3

`KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 3/3`

- frame bytes: `45`
- frame SHA256: `e0377d1ca3d05c696a02ae5a5671ffeb32cfde4ad5b7467e6ed3605aed889f9b`
- selectors: `745`
- packed selector bytes: `94`
- packed SHA256: `f0c58606e7fe11e4a0b3c86864280bfde23b04b5130fb8a86ddfd1116ec5379e`
- expected generated samples: `11920`

## Harness boundary

Tool: `tools/qualify_tx_sequence_r2.py`

The only CLI controls are:

- `--transmit`
- `--confirm P13B-R2-145050-P200-VERIFY-3`

There are no caller-selectable target, device, frequency, power, callsign, destination, payload, frame count, pause, or serializer timing options.

The physical sequence is bounded to at most three fixed submissions. Each submission is made once. Any internal failure stops execution; there is no automatic retry.

## Host qualification gates

CI locks:

- exact 145.050 MHz / `200/255` SET_FREQ bytes;
- setup only through the single `TXModemOwner` thread;
- frozen RX-only owner unchanged;
- exact three R2 AX.25/FCS vectors;
- exact 745-selector/94-byte Bell-202 vectors;
- exact `11920` expected samples per burst;
- reset-on-accepted-burst diagnostic semantics;
- no cumulative-delta accounting in the R2 tool;
- fixed 5.0 s gaps;
- at most three submissions;
- no automatic retry;
- dry-run returns before UART owner construction;
- no KISS/product TX wiring;
- no RF abort/exit, raw transact, flash, GPIO/reset, or option-byte path.

Expected host markers include:

```text
P13B_TX_QUALIFICATION_PROFILE=PASS
P13B_TX_FREQUENCY_HZ=145050000
P13B_TX_POWER=200
P13B_R2_THREE_TX_CONTRACT=PASS
RESET_ON_ACCEPT_COUNTER_SEMANTICS=PASS
R2_FIXED_FRAMES=3
R2_SELECTORS_PER_FRAME=745
R2_SAMPLES_PER_FRAME=11920
R2_INTER_PACKET_PAUSE_SECONDS=5.0
AUTOMATIC_TX_RETRY=NO
KISS_TX_CONNECTED=NO
PRODUCT_TX_ENABLED=NO
RF_TRANSMITTED_BY_CI=NO
```

## Physical acceptance still required

P13b remains open until R2 physical execution provides:

1. exact packet firmware identity;
2. three internally completed fixed bursts, unless execution safely stops on a failure;
3. per-burst `keyups == 1`;
4. per-burst `generated_samples == 11920`;
5. modem idle after each burst;
6. clean UART release;
7. at least one independent external decoder receiving an exact `P13B R2 VERIFY n/3` frame.

Only then may the P13b physical TX boundary be marked qualified. Ordinary KISS-originated TX remains disconnected after this test.
