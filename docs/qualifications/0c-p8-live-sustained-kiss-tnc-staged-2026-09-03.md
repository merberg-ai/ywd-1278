# 0C-P8 guarded physical sustained KISS TNC — staged

Date: 2026-09-03

Status: **staged / physical qualification pending**

Base checkpoint: `checkpoint/0c-p8-sustained-kiss-tnc-host-qualified` at `a835d2500dbdb4a8eaf1ae3cae4ea662203a852a`.

Initial live staging commits:

- `931b92ac015dc79449b6b7056ab015bd77575da7` — fixed physical vectors and safety manifest;
- `de5954383d216245be68852c34d26c2a249edfe0` — guarded sustained physical harness.

The live staging branch adds qualification-only tests, CI and documentation around those files. It does not change the frozen host-qualified P8/P7/P6/P4e/P5, modem-owner, Bell-202 or CSMA implementation sources.

## Physical qualification boundary

The staged test uses the already-qualified AX25R4 firmware and real POSIX modem path:

`two localhost KISS client sessions -> SustainedTNCBackend -> ThreadSafeKISSDataAdmissionQueue -> frozen P7/P6/P2/P1 -> frozen P4e -> frozen P5 -> real TXModemOwner -> /dev/ttyAMA0 -> AX25R4 firmware`

Locked physical parameters:

- frequency: `145.050 MHz`;
- RF power byte: `200/255`;
- source: `KJ6YWD-10`;
- destination: `YWD8`;
- literal path: `YWDNOD`;
- exactly three KISS-originated DATA bodies;
- KISS ingress contains no FCS; the TNC appends FCS exactly once;
- TXDELAY sequence: `30`, `50`, `30`;
- PERSIST: `63`;
- SLOTTIME: `10`;
- FULLDUPLEX: `0`;
- queue capacity: one physical request at a time;
- maximum TX submissions: exactly three;
- automatic TX retry: forbidden.

Each of the three cycles must independently prove:

1. one fixed DATA request was admitted with its immutable KISS parameter generation;
2. a fresh FCS-valid inbound frame that is not one of the P8 qualification frames was decoded;
3. real RSSI reached the qualified BUSY region (`raw <= 83`);
4. after qualified CLEAR (`raw >= 90`) and a full 100 ms slot, forced persistence byte `255` deferred;
5. after another full slot, forced byte `0` dispatched;
6. the real half-duplex lifecycle completed `RX_STOP -> TX -> RF idle -> RX_START`;
7. RX remained active with zero FIFO dropped bytes after the cycle;
8. the Bell-202 streaming decoder was reset after the TX discontinuity.

After cycle 1 the first TCP KISS client disconnects and a second client reconnects for cycles 2 and 3. After cycle 3, with the TX queue empty, one additional fresh non-P8 FCS-valid inbound frame must decode and be delivered through the live KISS connection. At least four non-qualification inbound frames are therefore required in total.

## Locked TX vectors

1. `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 1/3`
   - TXDELAY `30`, 45 opening flags, 785 selectors, 12560 generated samples.
2. `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 2/3`
   - TXDELAY `50`, 75 opening flags, 1025 selectors, 16400 generated samples.
3. `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 3/3`
   - TXDELAY `30`, 45 opening flags, 785 selectors, 12560 generated samples.

Independent direct RF decode of all three exact transmissions is required before qualification may be promoted. Observation of `YWDNOD*` remains deferred and non-blocking.

## Arming and rerun safety

Default invocation is dry-run only. It must exit before constructing `TXModemOwner`, creating the KISS listener, opening `/dev/ttyAMA0`, or transmitting RF.

Physical mode requires both the exact command-line token:

`P8-LIVE-145050-P200-SUSTAINED-3`

and the interactive phrase:

`TRANSMIT-P8-SUSTAINED-KISS-THREE`

If a failure occurs after any TX has been accepted, the full harness must not be rerun automatically or casually. Preserve the complete output and independent receiver evidence first. The harness explicitly emits `DO_NOT_RERUN_FULL_P8_LIVE_HARNESS=YES` in that case.

## CI gate

`p8-live-ci` is dedicated to the physical staging branch and must pass before RF execution. It verifies:

- the exact locked manifest and frame vectors;
- dry-run hardware inactivity;
- absence of arbitrary frequency/power/payload/count/retry CLI controls;
- absence of direct raw-transmit, raw-transact, flash, reset or option-byte escape paths;
- byte-identical host-qualified P8/P7/P6/P4e/P5, modem and Bell-202 source boundaries;
- hardened P8 sustained concurrency/integration regressions;
- P7 KISS ingress and live-evidence contracts;
- P6 controls, P5 TXDELAY, P4e lifecycle, CSMA, RSSI detector, modem protocol/transport and Bell-202 regressions.

## Safety boundary

This staging does not enable persistent product transmission.

- product TX: disabled;
- daemon TX: disabled;
- systemd TX: disabled;
- generic transmitter UI: absent;
- arbitrary RF parameters: absent;
- flash writes: forbidden;
- GPIO/reset operations: forbidden;
- option-byte operations: forbidden;
- automatic frame retry: absent.

Physical qualification remains pending until the guarded live test and independent direct external decode both succeed.
