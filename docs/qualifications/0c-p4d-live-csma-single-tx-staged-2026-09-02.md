# 0C-P4d — guarded live CSMA-controlled single TX

**Status:** STAGED / NOT PHYSICALLY RUN

## Purpose

0C-P4d is the first guarded physical composition of the qualified channel-access stack with the real modem UART and RF transmitter:

`live AX25R4 RSSI -> P2 detector -> P1 CSMA -> P4a bounded queue -> P13a TXBroker -> TXModemOwner -> POSIX /dev/ttyAMA0`

It does not connect KISS or the product daemon to TX. It is a single fixed qualification packet only.

## Frozen base

- checkpoint: `checkpoint/0c-p4c-real-owner-fake-transport-qualified`
- SHA: `e137b98b86b70b6835990c35f192741f0cb496e8`
- firmware already installed: qualified AX25R4 RSSI image
- frequency: `145.050 MHz`
- RF power: `200/255`, reusing the physically qualified P13b level

## Fixed packet

`KJ6YWD-10>YWD4D:YWD-1278 P4D CSMA VERIFY 1/1`

Locked vector:

- frame bytes: `46`
- frame SHA256: `2f700a4dd7675473a183e119b711ed44c1f0a1ed3a70505523c63af8d42d6655`
- opening/closing flags: `45 / 3`
- selectors: `753`
- packed selector bytes: `95`
- packed selector SHA256: `ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca`
- expected STM32 generated samples: `12048`

## Channel-access proof required in the same run

The queued frame cannot dispatch merely because the channel starts quiet. Before the first observed live BUSY event, every persistence trial is forced to byte `255`, which always defers under frozen `PERSIST=63`.

After a real RSSI BUSY observation (`raw <= 83`), the run must prove:

1. BUSY forces P1 to `WAIT_CLEAR` and cancels any prior slot.
2. `RECENT_RX` remains busy-for-access.
3. detector CLEAR requires its qualified 250 ms hold.
4. P1 then receives a fresh full 100 ms slot.
5. explicit byte `255` defers the first post-busy trial.
6. only a later full-slot trial with explicit byte `0` may reach READY and synchronously dispatch the fixed frame.

The maximum bounded request lifetime is 30 seconds from enqueue.

## Physical TX limits

- maximum submissions: **1**
- automatic retry: **NO**
- operator-selectable frequency/power/payload/count: **NO**
- exact CLI confirmation token required: `P4D-145050-P200-CSMA-VERIFY-1`
- exact interactive phrase required: `TRANSMIT-P4D-CSMA-VERIFY-ONE`
- UART must be unowned before opening
- exact AX25R4 runtime identity required
- modem must be TX-idle before setup and before broker dispatch
- completed burst diagnostics must be exactly one keyup and `12048` generated samples under the firmware's reset-on-accept counter semantics
- queue and broker must record exactly one dispatch/submission
- no duplicate dispatch after the completed burst

## Independent receiver requirement

A successful harness run is **not** by itself final P4d qualification. An independent receiver must decode exactly:

`KJ6YWD-10>YWD4D: YWD-1278 P4D CSMA VERIFY 1/1`

Only after that external evidence is supplied may the physical qualification be promoted.

## Explicitly still disconnected

- ordinary KISS TX: **NO**
- daemon/product TX: **NO**
- firmware flash: **NO**
- GPIO/reset: **NO**
- option-byte writes: **NO**

The dry-run form of the harness exits before `TXModemOwner` is constructed and therefore opens no UART and transmits no RF.
