# 0C-P2 AX25R4 RSSI Artifact + Live Activation Staging — 2026-09-02

Status: **ARTIFACT LOCKED / LIVE ACTIVATION STAGED — PHYSICAL AX25R4 RUN NOT YET EXECUTED**

## Physical boundary retained

The latest physically qualified target remains:

`0b-p13b-known-packet-tx-qualified`

The HAT is expected to start this phase running the exact P13b-qualified AX25R3 packet firmware:

- artifact: `firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`
- size: `59812`
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- identity: `MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

P13b physical TX evidence remains frozen and unchanged.

## Exact AX25R4 candidate build evidence

The target Pi built the self-contained AX25R4 candidate with:

`python3 firmware/build-packet-rssi-ywd1278.py`

The two independent builds were byte-identical:

- `REPRODUCIBLE_BUILDS=PASS`
- `YWD1278_0C_P2_RSSI_FIRMWARE_BUILD=PASS`
- artifact size: `59892`
- artifact SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- vector initial SP: `0x20005000`
- vector reset: `0x080080ad`
- identity count: `1`
- RF configured during build: `NO`
- flash written during build: `NO`
- option bytes written during build: `NO`

Exact candidate:

`firmware/out/0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1-7ff74ed-hse8m.bin`

Identity:

`MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

The candidate is exactly `80` bytes larger than the physically qualified AX25R3 artifact. That delta is recorded as continuity information only; qualification relies on the exact artifact hash and behavior gates, not the size delta.

## Artifact lock

The exact physical transition is frozen in:

`firmware/qualification/0c-p2-rssi-live-stage.json`

The staging manifest locks:

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- physical base: exact P13b AX25R3 artifact/identity
- candidate: exact 59892-byte AX25R4 artifact
- candidate SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- UART: `/dev/ttyAMA0`
- receive frequency: `145050000` Hz
- RSSI observation: `20.0` s
- RSSI polling: `0.05` s
- confirmation token: `QUALIFY-0C-P2-RSSI-RX-ONLY`

No carrier threshold or hysteresis is selected.

## Guarded physical activation

`firmware/activate-rssi-live.sh` is a one-purpose qualification wrapper. It does **not** accept operator overrides for target, UART, frequency, firmware, observation length, RSSI polling interval, threshold, or hysteresis.

Before the candidate write it requires:

1. normal product `flash_enabled=false`;
2. target status still exactly `0b-p13b-known-packet-tx-qualified`;
3. exact AX25R3 rollback artifact available locally;
4. exact AX25R4 candidate available locally;
5. the protected two-pass stock backup;
6. no competing modem service and no existing UART owner;
7. exact running AX25R3 GET_VERSION identity;
8. a bootloader readback of the current programmed AX25R3 prefix matching SHA256 `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`.

Only then can the operator pass the explicit qualification token and interactive activation confirmation.

The wrapper writes only the exact locked AX25R4 candidate, verifies its programmed prefix SHA256, restarts the application, and requires the exact AX25R4 identity before the RSSI observation starts.

### Automatic recovery

The wrapper marks a candidate write as attempted **before** invoking `stm32flash`. Therefore even a partially failed candidate write enters automatic recovery.

Failure recovery order is:

1. restore the exact P13b-qualified AX25R3 artifact;
2. verify its programmed prefix SHA256;
3. restart and verify the exact AX25R3 identity;
4. only if AX25R3 rollback itself fails, restore the protected exact stock image, perform the complete 128 KiB readback, and verify the exact stock identity.

No STM32 option-byte operation exists in the wrapper.

## Receive-only RSSI observation

`tools/qualify_live_rssi.py` uses only the base `ModemOwner`; it never constructs `TXModemOwner`, `TXBroker`, KISS TX, or a selector-burst operation.

The sequence is:

- exact AX25R4 GET_VERSION gate;
- fixed simplex receive `SET_FREQ` at 145.050 MHz;
- fixed receive-safe modem I/O setup;
- RF idle diagnostics;
- `YWD_RX START`;
- continuous raw FIFO draining;
- bounded `YWD_RX/0x05` RSSI polling;
- periodic RX FIFO/status checks;
- `YWD_RX STOP` and final FIFO drain;
- RF diagnostic comparison before/after.

The raw receive FIFO is drained continuously because the qualified 19.2 ksample/s slicer produces about 2400 packed bytes/s while the firmware FIFO is only 512 bytes deep.

The tool prints every raw RSSI sample and a summary containing minimum, p05, median, p95, maximum, and distinct-value count. These values are observational data only.

A successful observation requires:

- exact AX25R4 identity;
- active RX flags remain `0x0D`;
- final idle RX flags `0x04`;
- firmware receive samples advance;
- zero RX FIFO drops;
- RF keyup diagnostics unchanged;
- RF TX generated-sample diagnostics unchanged;
- TX inactive before and after;
- one modem owner releases the UART;
- no carrier/busy threshold chosen.

## Safety boundary

Still disconnected/not enabled:

- ordinary TCP KISS-originated TX;
- persistent product TX;
- CSMA-to-broker integration;
- automatic TX retry;
- carrier threshold;
- hysteresis;
- busy/clear classification.

The AX25R4 firmware inherits the already-qualified packet TX engine, but the P2 live observation process has no TX API and issues no TX command.

## Next physical evidence

The immediate physical run should establish:

1. exact AX25R3 starting bytes and identity;
2. exact AX25R4 programmed bytes and identity;
3. live raw ADF7021 RSSI telemetry while passive receive capture is active;
4. zero TX activity during the observation;
5. the raw RSSI distribution on 145.050 MHz.

A successful first RSSI run does **not** by itself complete 0C-P2. We still need signal-vs-idle characterization sufficient to select and independently test a conservative threshold/hysteresis policy before wiring the live sensor into the already host-qualified 0C-P1 CSMA state machine.
