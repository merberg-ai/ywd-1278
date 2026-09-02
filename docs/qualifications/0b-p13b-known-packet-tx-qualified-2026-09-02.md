# YWD-1278 0B-P13b Known-Packet TX Qualification — 2026-09-02

Status: **QUALIFIED**

## Qualification boundary

0B-P13b qualifies the first guarded YWD-1278 known-packet RF transmit path on the reference simplex MMDVM_HS HAT. It does **not** connect ordinary TCP KISS clients or the persistent product daemon to TX. Those paths remain disabled pending channel-access / CSMA work.

Target:

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- device: `/dev/ttyAMA0`
- packet firmware identity: `MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- RF frequency: `145.050 MHz`
- qualification RF power: `200/255`
- Bell-202 serializer: frozen P5 profile, 45 opening flags, 3 closing flags, initial MARK

## Historical attempts retained

The original P13b one-shot was not discarded or rewritten. It internally passed with exactly one submission, keyups `0->1`, generated samples `0->12048`, idle completion, clean UART release, no flash/GPIO/option-byte activity, and no automatic retry. Independent external decode was not confirmed for that first run.

P13b-R1 then attempted a three-packet decode-assist sequence at the minimum SET_FREQ RF power `1/255`. Burst 1 was submitted, but the host verifier incorrectly treated firmware TX diagnostics as lifetime counters. The firmware resets `keyups` and generated-sample diagnostics on every accepted burst, so R1 produced a false-negative `keyup delta=0` after the first burst and stopped before bursts 2/3. R1 remains preserved as a partial physical attempt.

P13b-R2 corrected both issues:

- per-burst reset-on-accept diagnostic semantics are checked directly;
- RF power uses `200/255`, the same level previously independently decoded during the frozen AX25-5B lineage.

## Frozen R2 transmit sequence

Exactly three fixed frames were submitted through `TXBroker` and `TXModemOwner`; no user-selectable source, destination, payload, frequency, power, count, timing, or serializer parameters were exposed.

1. `KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 1/3`
2. `KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 2/3`
3. `KJ6YWD-10>YWD13B:YWD-1278 P13B R2 VERIFY 3/3`

Each frame is:

- FCS-bearing AX.25 bytes: `45`
- Bell-202 selectors: `745`
- packed selector bytes: `94`
- expected generated samples: `11920`
- nominal selector duration: `745 / 1200 = 0.620833... s`

The harness inserts a fixed `5.0 s` pause between burst 1/2 and burst 2/3. There is no automatic retry.

## Internal physical evidence

The target reported all three bursts complete:

```text
BURST[1]_TX=COMPLETE
BURST[1]_KEYUPS_ABSOLUTE=1
BURST[1]_GENERATED_SAMPLES_ABSOLUTE=11920
BURST[1]_COUNTERS_RESET_ON_ACCEPT=PASS
PAUSE_AFTER[1]=5.0s
BURST[2]_TX=COMPLETE
BURST[2]_KEYUPS_ABSOLUTE=1
BURST[2]_GENERATED_SAMPLES_ABSOLUTE=11920
BURST[2]_COUNTERS_RESET_ON_ACCEPT=PASS
PAUSE_AFTER[2]=5.0s
BURST[3]_TX=COMPLETE
BURST[3]_KEYUPS_ABSOLUTE=1
BURST[3]_GENERATED_SAMPLES_ABSOLUTE=11920
BURST[3]_COUNTERS_RESET_ON_ACCEPT=PASS
TRANSMIT_SUBMISSIONS=3
COMPLETED_BURSTS=3
YWD1278_0B_P13B_R2_INTERNAL_THREE_TX=PASS
EXACT_PACKET_FIRMWARE_IDENTITY=PASS
QUALIFIED_RF_POWER_200_255=PASS
RESET_ON_ACCEPT_COUNTER_ACCOUNTING=PASS
THREE_FIXED_TX_SUBMISSIONS=PASS
THREE_COMPLETED_KEYUPS=PASS
THREE_EXACT_GENERATED_SAMPLE_COUNTS=PASS
FIXED_FIVE_SECOND_GAPS=PASS
MODEM_UART_RELEASED=YES
KISS_TX_CONNECTED=NO
PRODUCT_TX_ENABLED=NO
FLASH_WRITTEN=NO
GPIO_ACCESSED=NO
OPTION_BYTES_WRITTEN=NO
AUTOMATIC_TX_RETRY=NO
EXTERNAL_DECODE_REQUIRED=YES
```

## Independent over-air decode

A physically separate 1200-baud packet receiver/decoder on 145.050 MHz decoded all three exact R2 frames:

```text
15:50:47 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 1/3
15:50:53 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 2/3
15:50:59 RX vhf KJ6YWD-10>YWD13B: YWD-1278 P13B R2 VERIFY 3/3
```

The qualification required only one exact external decode; all three were observed. Unrelated channel traffic seen by the decoder is intentionally excluded from the acceptance evidence.

## Safety properties retained

- exact packet firmware identity required before TX;
- fixed 145.050 MHz qualification frequency;
- fixed `200/255` qualification RF power;
- exactly three known R2 frames in the successful qualification run;
- fixed 5-second inter-packet gaps;
- no automatic transmit retry;
- bounded P13a broker path only;
- ordinary TCP KISS TX remains disconnected;
- persistent product TX remains disabled;
- no firmware flash;
- no GPIO/reset activity;
- no STM32 option-byte writes;
- modem UART released after completion.

## Qualification conclusion

**0B-P13b is QUALIFIED.**

YWD-1278 has now independently demonstrated that the frozen host AX.25/Bell-202 serializer, bounded TX broker, single UART-owner TX command path, packet firmware waveform engine, ADF7021 RF path, and an ordinary external 1200-baud packet decoder interoperate over the air on 145.050 MHz.

This qualification does **not** authorize wiring arbitrary KISS-originated TX into the product. The next TX work must add deterministic channel-access / CSMA policy before KISS-originated transmission is connected and independently requalified.
