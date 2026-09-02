# 0B-P13b Internal Single-TX Evidence — 2026-09-02

Status: **INTERNAL RF TX PASSED — EXTERNAL DECODE UNVERIFIED**

This record preserves the first physical 0B-P13b one-shot transmit attempt exactly as observed. It is not a full P13b qualification because the independently monitored receiver/decoder did not produce a confirmed decode of the packet.

The original staged vector and the frozen staging checkpoint `checkpoint/0b-p13b-single-tx-staged-green` remain historical and must not be rewritten.

## Physical test

Target:

`mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`

UART:

`/dev/ttyAMA0`

Running packet identity:

`MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Transmit frequency:

`145050000 Hz`

Frozen RF power field:

`1/255`

Known packet:

`KJ6YWD-10>YWD13B:YWD-1278 P13B SINGLE TX TEST`

AX.25 / Bell-202 vector:

- frame bytes: `46`
- frame SHA256: `06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87`
- selector count: `753`
- packed selector bytes: `95`
- packed selector SHA256: `7b99563d208029084af0559484ed38afbced3d01e9ec28610883efb5931e88b1`
- nominal burst: `0.6275 s`
- expected generated samples: `12048`

## Observed internal RF evidence

The physical run reported:

```text
TRANSMIT_SUBMISSIONS=1
BROKER_FRAME_BYTES=46
BROKER_FRAME_SHA256=06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87
BROKER_SELECTOR_COUNT=753
BROKER_PACKED_SELECTOR_BYTES=95
BROKER_PACKED_SELECTOR_SHA256=7b99563d208029084af0559484ed38afbced3d01e9ec28610883efb5931e88b1
RF_KEYUPS=0->1
RF_KEYUP_DELTA=1
RF_TX_GENERATED_SAMPLES=0->12048
RF_TX_GENERATED_SAMPLES_DELTA=12048
RF_STATUS_REMAINING=0->0
RF_TX_ACTIVE=0->0
```

Internal pass markers:

```text
YWD1278_0B_P13B_INTERNAL_SINGLE_TX=PASS
EXACT_PACKET_FIRMWARE_IDENTITY=PASS
P13A_BOUNDED_BROKER_PATH=PASS
ONE_TX_SUBMISSION_ONLY=PASS
EXPECTED_ONE_RF_KEYUP=PASS
EXPECTED_GENERATED_SAMPLES=PASS
MODEM_UART_RELEASED=YES
KISS_TX_CONNECTED=NO
PRODUCT_TX_ENABLED=NO
FLASH_WRITTEN=NO
GPIO_ACCESSED=NO
OPTION_BYTES_WRITTEN=NO
AUTOMATIC_TX_RETRY=NO
EXTERNAL_DECODE_REQUIRED=YES
```

Therefore the host/broker/firmware chain produced exactly the internally expected bounded RF activity:

- one broker submission;
- one RF keyup;
- exactly `12048` generated samples;
- no residual selectors;
- TX inactive after completion;
- UART released;
- no flash, GPIO/reset, option-byte, KISS-originated, or persistent product TX path.

## Missing qualification evidence

The separate receiver/decoder did not provide a confirmed decode of the expected packet. This means the run proves that the bounded command reached the packet firmware and caused the expected RF-generation counters, but does **not** independently prove the over-air Bell-202/AX.25 content.

P13b therefore remains unqualified.

## Follow-up: P13b-R1 external-decode assist sequence

To improve the probability of independent observation without opening an unrestricted TX path, the next staged test may transmit exactly three fixed known packets at 145.050 MHz, separated by fixed pauses. Each packet must have a distinct sequence marker (`1/3`, `2/3`, `3/3`).

The retry sequence must remain bounded:

- exactly three fixed vectors;
- no user-selectable payload/frequency/count;
- fixed inter-packet delay;
- no automatic retry after a failed broker submission;
- KISS-originated and persistent product TX remain disconnected;
- exact packet-firmware identity and idle-modem gates remain mandatory;
- internal RF counters must prove exactly three keyups and the exact aggregate generated-sample count;
- at least one independently decoded fixed vector is required to finish physical P13b qualification.
