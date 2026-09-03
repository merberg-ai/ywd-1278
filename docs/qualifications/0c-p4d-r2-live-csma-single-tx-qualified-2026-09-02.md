# 0C-P4d-R2 — guarded live CSMA single-TX qualification

Date: 2026-09-02

Status: **physically qualified**

## What this proves

0C-P4d-R2 physically composed the previously qualified channel-access and TX layers against the real MMDVM_HS HAT:

`live AX25R4 RSSI -> P2 busy detector -> P1 p-persistent CSMA -> bounded P4a request -> real TXBroker -> real TXModemOwner -> real POSIX /dev/ttyAMA0 transport -> one RF burst`

The test was deliberately limited to one fixed qualification frame and required a real observed BUSY event before any RF transmission could become eligible. KISS-originated TX and persistent product TX remained disconnected.

## Exact hardware/runtime profile

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- running firmware identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- RX/TX frequency: `145050000` Hz
- RF power: `200/255`, reused from the frozen P13b physical qualification
- detector: BUSY `<=83`, CLEAR release `>=90`, recent-RX/continuous-clear hold `250 ms`
- P1: `PERSIST=63`, `SLOTTIME=10` (`100 ms`), maximum wait `30 s`

## Exact transmitted vector

Expected and independently decoded packet:

`KJ6YWD-10>YWD4D:YWD-1278 P4D CSMA VERIFY 1/1`

Locked vector:

- frame bytes: `46`
- frame hex: `b2ae88688840e096946cb2ae887503f05957442d31323738205034442043534d412056455249465920312f310a32`
- frame SHA256: `2f700a4dd7675473a183e119b711ed44c1f0a1ed3a70505523c63af8d42d6655`
- Bell-202 selectors: `753`
- packed selector bytes: `95`
- packed selector SHA256: `ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca`
- expected generated samples: `12048`

## Live channel-access evidence

The harness began in active AX.25 receive mode and drained the receive FIFO while polling RSSI every 50 ms.

Before the real BUSY event, every persistence draw was forced to `255`. The system performed **81 pre-busy deferral trials** without transmitting.

Observed transition sequence:

- BUSY: `10.700 s`, raw RSSI `48`
- BUSY forced P1 back to `WAIT_CLEAR`
- RECENT_RX remained busy-for-access
- CLEAR: `11.800 s`
- first full post-clear persistence trial: `11.900 s`, byte `255`, defer
- second full-slot trial / dispatch: `12.050 s`, byte `0`, READY

The first post-clear trial occurred exactly `100 ms` after CLEAR. Dispatch occurred `150 ms` after that deferral, satisfying the frozen full-slot requirement again.

Receive-side counters before the TX handoff:

- RSSI samples: `242`
- packed RX bytes drained: `28942`
- RX status checks: `46`
- FIFO dropped bytes: `0`

## Required half-duplex RX -> TX handoff

P4d-R2 explicitly proved the firmware-required half-duplex lifecycle:

1. `RX_START`
2. verify active RX3 state
3. poll RSSI while draining the FIFO
4. require live BUSY and complete P2/P1 access sequence
5. after READY, issue `RX_STOP`
6. verify passive RX is inactive
7. only then call `TXBroker.submit_frame()`
8. permit exactly one fixed RF burst

This handoff is mandatory because the qualified firmware intentionally rejects `YWD_RF/TX_TONES` while passive AX.25 RX capture is active.

## TX evidence

- transmit submissions: `1`
- broker frame bytes: `46`
- broker selector count: `753`
- broker packed-selector bytes: `95`
- broker packed-selector SHA256: `ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca`
- duplicate dispatch: **NO**
- automatic retry: **NO**
- single modem owner: **PASS**
- UART released: **YES**

Firmware TX diagnostics are **reset on each accepted selector burst**. Therefore the following are absolute completed-burst values, not lifetime deltas:

- diagnostics before this submission: keyups `1`, generated samples `12048`
- completed P4d burst absolute keyups: `1`
- completed P4d burst absolute generated samples: `12048`

The identical before/after absolute values must not be interpreted as evidence of no transmission; accepting this P4d burst resets those counters. The one accepted broker submission, reset-on-accept completed diagnostics, and independent over-air decode together are the qualification evidence.

## Independent over-air decode

The independent receiver captured the exact expected frame at local timestamp `19:45:13`:

`RX vhf  KJ6YWD-10>YWD4D: YWD-1278 P4D CSMA VERIFY 1/1`

This satisfies the staged requirement for at least one independently decoded exact P4d frame.

## Safety results

- KISS TX connected: **NO**
- persistent product TX enabled: **NO**
- maximum submissions: **1**
- automatic TX retry: **NO**
- flash written: **NO**
- GPIO/reset accessed: **NO**
- option bytes written: **NO**
- RF transmitted: **YES — exactly one bounded qualification burst**

## Preserved R1 failure

The original P4d-R1 staging checkpoint remains frozen at:

`checkpoint/0c-p4d-live-csma-single-tx-staged-green`

`d2ff131b989ad4fe81baa8a86067383e98e66c73`

R1 physically failed before any TX submission because it attempted `RX_RSSI` without first issuing `YWD_RX/RX_START`; AX25R4 correctly returned MMDVM NAK. R2 also corrected the next required lifecycle boundary by explicitly stopping RX before `TX_TONES` and continuously draining the FIFO while waiting for access.

R1 recorded zero TX submissions and no RF transmission. It is historical evidence and must not be rewritten.

## Boundary after P4d

P4d-R2 qualifies the real physical CSMA-controlled single-packet path. It does **not** authorize general or KISS-originated TX. The next phase may build persistent half-duplex scheduling around this exact RX -> channel access -> RX_STOP -> TX -> RX restart lifecycle, with bounded queues and existing KISS TX still disconnected until separately qualified.
