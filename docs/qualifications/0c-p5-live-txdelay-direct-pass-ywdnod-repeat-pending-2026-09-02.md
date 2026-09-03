# 0C-P5 live — TXDELAY physical execution passed; YWDNOD repeat proof pending

Date: 2026-09-02

Status: **physical TXDELAY execution passed; full P5 live qualification remains pending the independent `YWDNOD*` repeat gate**

Run-ready checkpoint: `checkpoint/0c-p5-live-txdelay-ywdnod-r3-staged-green` at `634e796cbc862ed0541351ffc2aa66b780731f7c`.

Host TXDELAY checkpoint: `checkpoint/0c-p5-txdelay-host-qualified` at `30cc677fbcc9fc9bab1aa1a18c18850ed1ef40a1`.

## Result

The guarded P5 R3 entry point completed its reviewed R2 physical core on the AX25R4 MMDVM HAT at 145.050 MHz / RF power `200/255`.

Exactly two fixed packets were transmitted through the literal AX.25 path `VIA YWDNOD`:

1. `KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 300MS 1/2`
2. `KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 500MS 2/2`

Both half-duplex cycles completed successfully and the independent AXConsole receiver displayed both outgoing packets. The first used TXDELAY `30` = 300 ms = 45 opening flags and generated exactly `13072` samples. The second used TXDELAY `50` = 500 ms = 75 opening flags and generated exactly `16912` samples.

This physically confirms the intended TXDELAY timing change and preserves the qualified RX -> channel access -> RX_STOP -> TX -> RF-idle -> RX_START lifecycle.

## Live counters

- complete RX/TX/RX cycles: `2`
- initial RX starts: `1`
- post-TX RX restarts: `2`
- total RX starts: `3`
- TX submissions: `2`
- total FCS-valid inbound frames: `5`
- qualifying non-P5 inbound frames: `3`
- returned P5 qualification frames ignored as authorization/proof: `2`
- fresh pre-TX non-P5 decoded triggers: `2`
- final post-TX non-P5 FCS-valid RX: **PASS**
- RSSI samples: `504`
- packed RX bytes drained: `110093`
- RX status checks: `174`
- peak FIFO available: `105` bytes
- FIFO dropped bytes: `0`
- one modem owner: **PASS**
- UART released: **YES**

## Per-cycle TXDELAY proof

Cycle 1:

- TXDELAY units: `30`
- requested delay: `300 ms`
- opening flags: `45`
- selectors: `817`
- completed-burst keyups: `1`
- expected/observed generated samples: `13072 / 13072`
- live BUSY: **PASS**
- fresh non-P5 RX trigger: **PASS**
- persistence `255` defer: **PASS**
- persistence `0` dispatch: **PASS**
- RX_STOP -> TX -> RX restart: **PASS**
- detector CLEAR to defer: `0.100 s`
- defer to dispatch: `0.150 s`

Cycle 2:

- TXDELAY units: `50`
- requested delay: `500 ms`
- opening flags: `75`
- selectors: `1057`
- completed-burst keyups: `1`
- expected/observed generated samples: `16912 / 16912`
- live BUSY: **PASS**
- fresh non-P5 RX trigger: **PASS**
- persistence `255` defer: **PASS**
- persistence `0` dispatch: **PASS**
- RX_STOP -> TX -> RX restart: **PASS**
- detector CLEAR to defer: `8.900 s`
- defer to dispatch: `0.100 s`

The long cycle-2 CLEAR-to-defer interval is not a SLOTTIME failure. It reflects the time until the detector/channel-access state became eligible for the first post-clear deterministic persistence trial; once a trial occurred, the subsequent defer-to-dispatch interval was one full 100 ms slot.

## Independent external direct-decode proof

The operator supplied an AXConsole screenshot showing both exact P5 packets:

- `04:21:49` — `KJ6YWD-10 > YWD5TD`, `via YWDNOD`, `YWD-1278 P5 TXDELAY 300MS 1/2`
- `04:22:00` — `KJ6YWD-10 > YWD5TD`, `via YWDNOD`, `YWD-1278 P5 TXDELAY 500MS 2/2`

Therefore the independent direct-decode gate is `2/2` and satisfied.

The same screenshot later displays an unrelated path as `KRDG*,KBANN`, proving AXConsole visibly marks a repeated/H-bit path entry with `*`. Neither P5 packet is shown with `YWDNOD*` in the supplied evidence. Accordingly **no claim is made that KJ6YWD-5/YWDNOD repeated either P5 packet**.

## Returned qualification traffic was correctly excluded

After the second TX/restart, the live harness decoded another copy of the 500 ms P5 frame and printed:

`FINAL_QUALIFICATION_ECHO_IGNORED_AS_RX_PROOF=YES`

It then decoded the non-qualification frame:

- source: `KJ6YWD`
- destination: `JIM`
- path: `KRDG,KBANN`
- information: `yay it works`

That non-P5 frame satisfied the final RX proof. The returned P5 traffic did not authorize another TX and did not satisfy the final receive gate.

## Safety result

The successful run reported:

- duplicate dispatch: **NO**
- automatic TX retry: **NO**
- KISS parameter ingress: **DISCONNECTED**
- KISS DATA TX: **DISCONNECTED**
- product TX: **DISABLED**
- flash written: **NO**
- GPIO accessed: **NO**
- option bytes written: **NO**
- RF transmitted: **YES, exactly two fixed qualification bursts**

## Promotion consequence

The physical TXDELAY behavior itself is proven and both fixed packets were independently decoded over the air. However, the separately locked P5 live promotion gate also requires two independent `YWDNOD*` repeated decodes. The supplied evidence contains zero such marked repeats.

Therefore:

- direct TXDELAY physical gate: **PASS (2/2)**
- YWDNOD repeat gate: **PENDING (0/2 proven)**
- full 0C-P5 live physical qualification: **NOT YET COMPLETE**
- rerunning the completed two-burst harness: **NOT PERMITTED**

If additional RF is needed to investigate or prove YWDNOD repetition, it must be a new, separately staged, narrowly scoped qualification rather than a rerun of the completed two-burst P5 harness.
