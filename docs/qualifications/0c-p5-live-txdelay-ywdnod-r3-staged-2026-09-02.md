# 0C-P5-live R3 — guarded TXDELAY qualification VIA YWDNOD

Date: 2026-09-02

Status: **staged; not yet physically run**

Base: `checkpoint/0c-p5-txdelay-host-qualified` at `30cc677fbcc9fc9bab1aa1a18c18850ed1ef40a1`.

Authorized physical harness: `tools/qualify_live_p5_txdelay_ywdnod_r3.py`.

## Purpose

0C-P5 host qualification proved KISS-style TXDELAY policy without hardware. This gate asks the physical question using the already-qualified P4e persistent half-duplex lifecycle:

**Do the fixed 300 ms and 500 ms TXDELAY profiles produce the exact expected modem burst lengths and decode over air while attempting to use KJ6YWD-5 through AX.25 path `VIA YWDNOD`?**

KISS parameter ingress and KISS DATA TX remain disconnected. This is still a fixed qualification transmitter.

## Fixed RF profile

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- firmware: exact already-installed AX25R4 identity
- frequency: 145.050 MHz
- RF power: 200/255
- source: `KJ6YWD-10`
- destination: `YWD5TD`
- path: exactly `YWDNOD`
- digipeater station represented by that alias: `KJ6YWD-5`
- maximum TX submissions: exactly two
- automatic retry: none

No CLI argument can alter device, frequency, power, source, destination, path, frame content, TXDELAY profile, or transmit count.

## Locked vectors

### Cycle 1 — TXDELAY 30

`KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 300MS 1/2`

- TXDELAY = 30
- requested preamble = 300 ms
- opening flags = 45
- frame bytes = 54
- selectors = 817
- packed selector bytes = 103
- packed selector SHA256 = `534383e423bdf4f71cdafa3da9d1bbdb0bfc165e1a14d8fbd0fd676df15be145`
- expected generated samples = 13072

### Cycle 2 — TXDELAY 50

`KJ6YWD-10>YWD5TD,YWDNOD:YWD-1278 P5 TXDELAY 500MS 2/2`

- TXDELAY = 50
- requested preamble = 500 ms
- opening flags = 75
- frame bytes = 54
- selectors = 1057
- packed selector bytes = 133
- packed selector SHA256 = `f0c9b7c1e08fb9cf512fa6afa7d57b84e33f42af226e4d4957b00a6ca174cb22`
- expected generated samples = 16912

The 240-selector / 3840-sample difference is exactly the additional 30 opening flags required by the 200 ms TXDELAY increase.

## Per-cycle authorization

Each outgoing packet uses the already-qualified access/lifecycle chain:

`active RX -> RSSI detector -> P1 CSMA -> RX_STOP -> TXDelayBroker -> RF idle -> RX_START`

Before either TX can occur, both must have happened during that cycle:

1. live RSSI reached BUSY; and
2. a fresh FCS-valid **non-P5-qualification** inbound frame was decoded.

Before both conditions, every persistence trial is forced to 255. After both conditions, the harness requires one full 100 ms slot with 255 defer and another full slot with 0 dispatch.

## YWDNOD self-repeat exclusion

A successful digipeater repeat modifies the YWDNOD H/repeated bit and therefore changes frame bytes/FCS. The final R3 wrapper classifies qualification traffic semantically by:

- source `KJ6YWD-10`;
- destination `YWD5TD`; and
- either exact P5 qualification information field.

Thus both a direct/local echo and a true `YWDNOD*` repeated copy are decoded and visible but **cannot authorize the next TX** and cannot satisfy the final receive-only proof. This prevents our own digipeated qualification traffic from creating a self-triggering chain.

## Final RX proof

After the 500 ms cycle completes and RX restarts, no TX request is queued. The Pi must decode another FCS-valid non-P5 qualification frame. A returned P5 direct/repeated copy is explicitly ignored for this purpose.

## External receiver gate

Physical promotion requires four external observations in total:

1. direct decode of 300 ms packet, path `YWDNOD`;
2. repeated decode of that same packet showing consumed path, conventionally `YWDNOD*`;
3. direct decode of 500 ms packet;
4. repeated decode of that packet showing `YWDNOD*`.

If both direct frames and modem diagnostics pass but YWDNOD does not repeat one or both frames, TXDELAY/direct-RF evidence is successful but the **YWDNOD repeat gate remains incomplete**. Do not weaken the gate or rerun blindly; diagnose the digipeater/alias behavior separately.

## Staging corrections before physical use

No physical run occurred with the earlier staging scripts.

- R1 was superseded because failure-report accounting could conservatively double-count the active cycle after a post-TX diagnostic failure.
- R2 corrected accepted-TX accounting using an explicit active-cycle base, but its initial exact-byte qualification-echo classifier would not necessarily recognize a true digipeated copy because the H bit/FCS changes.
- R3 is the only authorized physical entry point. It preserves the R2 core and replaces echo classification with semantic matching independent of H bit/FCS.

## Failure/rerun safety

Accepted-TX count is derived exactly from completed prior cycles plus the current lifecycle/broker acceptance. Any failure after one or more accepted RF submissions prints a do-not-rerun marker. There is no automatic TX retry.

## Safety boundary

- KISS parameter ingress: disconnected
- KISS DATA TX: disconnected
- product TX: disabled
- maximum fixed transmissions: two
- automatic retry: none
- flash: none
- GPIO/reset: none
- option-byte operations: none
- exactly one modem owner

Do not run physically until the final R3 dry-run, static contract, manifest parse, P5 host guard, full framework suite, and historical P4d/P4e guards are green on the same exact staging head.
