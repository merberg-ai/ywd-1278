# 0B-P13b Guarded Single TX — Staged 2026-09-02

Status: **STAGED / CI-GREEN — PHYSICAL TX NOT YET RUN**

0B-P13b is the first physical YWD-1278 product-side transmit qualification above the host-qualified P13a bounded TX broker. The staging boundary is intentionally one-purpose and one-shot.

The physical HAT target remains at `0b-p12b-live-rf-kiss-qualified` until both the internal RF diagnostics and an independent external receiver/TNC prove the exact transmitted packet.

## Frozen test packet

The only packet admitted by the P13b qualification harness is:

`KJ6YWD-10>YWD13B:YWD-1278 P13B SINGLE TX TEST`

Frozen vector:

- frequency: `145.050 MHz`;
- AX.25 UI / PID `0xF0`;
- FCS-bearing frame bytes: `46`;
- frame hex: `b2ae88626684e096946cb2ae887503f05957442d3132373820503133422053494e474c4520545820544553545c59`;
- frame SHA256: `06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87`;
- P5 serializer profile: `45` opening flags, `3` closing flags, initial `MARK`;
- selector count: `753`;
- packed selector bytes: `95`;
- packed selector SHA256: `7b99563d208029084af0559484ed38afbced3d01e9ec28610883efb5931e88b1`;
- nominal burst duration: `0.6275 s`;
- firmware expansion: `16` samples/selector;
- expected generated-sample delta: `12048`.

## Physical harness safety boundary

`tools/qualify_single_tx.py` defaults to dry-run. Physical TX additionally requires both `--transmit` and the exact confirmation token `P13B-145050-ONE-SHOT`.

Before the one permitted submission the harness must:

1. prove the target is still at the frozen P12b physical boundary;
2. prove normal flashing and option-byte writes remain disabled;
3. prove P12a left the exact packet firmware installed;
4. prove the running `GET_VERSION` identity exactly matches the qualified P10/P11 AX25R3 packet image;
5. prove the modem reports zero pending selectors and TX inactive;
6. record baseline RF keyup/generated-sample counters;
7. configure the frozen simplex MMDVM profile at exactly `145050000 Hz`;
8. use the existing minimum nonzero SET_FREQ RF-power byte `1/255`;
9. prove frequency/config setup itself caused no keyup or generated-sample change.

Only then is a `TXBroker` constructed with `transmit_enabled=True` and queue capacity `1`.

The harness source contains exactly one `broker.submit_frame(...)` call. It has no transmit retry path. If the TX transaction fails or times out, the harness must not resubmit the packet.

## Required internal physical evidence

After the one submission, P13b requires:

- broker receipt frame SHA/count matches the frozen vector;
- selector count `753`;
- exactly one RF-keyup counter increment, modulo the firmware's 8-bit counter;
- exactly `12048` generated RF samples, modulo the firmware's 16-bit counter;
- TX returns inactive;
- remaining selectors return to zero;
- exactly one transmit submission;
- UART released after the owner shuts down;
- no flash;
- no GPIO/reset;
- no option-byte write;
- no automatic TX retry.

The internal harness may report `YWD1278_0B_P13B_INTERNAL_SINGLE_TX=PASS`, but that marker alone is deliberately insufficient to qualify P13b.

## Independent decode requirement

A physically separate receiver/TNC/decoder monitoring `145.050 MHz` must independently decode the exact packet as:

`KJ6YWD-10>YWD13B:YWD-1278 P13B SINGLE TX TEST`

That external evidence is required before the target manifest, roadmap, or final P13b checkpoint may be advanced to qualified.

## Product/KISS boundary remains closed

P13b does not connect TCP KISS DATA to TX. The existing KISS backend remains RX-only and continues to reject inbound DATA. The daemon constructs no TX broker or TX owner. Persistent product TX remains disabled.

P13b staging also contains no user-selectable frequency, source, destination, payload, serializer timing, or transmit-count arguments. Flash, GPIO/reset, option-byte, RF-abort, RF-exit, raw-transact, and repeated-transmit paths are absent from the harness.

## CI gate

The P13b contract locks:

```text
P13B_SINGLE_TX_CONTRACT=PASS
P12B_PHYSICAL_BOUNDARY_FROZEN=PASS
P13B_FREQUENCY_HZ=145050000
P13B_FRAME_VECTOR=PASS
P13B_SELECTOR_COUNT=753
P13B_PACKED_SELECTOR_BYTES=95
P13B_EXPECTED_GENERATED_SAMPLES=12048
MAX_TX_SUBMISSIONS=1
AUTOMATIC_TX_RETRY=NO
KISS_TX_CONNECTED=NO
PRODUCT_TX_ENABLED=NO
FLASH_PATH=ABSENT
GPIO_RESET_PATH=ABSENT
OPTION_BYTE_PATH=ABSENT
EXTERNAL_DECODE_REQUIRED=YES
RF_TRANSMITTED_BY_CI=NO
```

No CI job opens hardware or transmits RF.
