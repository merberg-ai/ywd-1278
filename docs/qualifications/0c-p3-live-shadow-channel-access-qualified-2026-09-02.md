# 0C-P3 live shadow channel access — physically qualified 2026-09-02

## Status

**PHYSICALLY QUALIFIED — shadow READY only; no transmit path connected.**

0C-P3 physically composed the already-qualified 0C-P2 RSSI busy/recent-RX detector with the already-qualified 0C-P1 p-persistent CSMA policy on the real first supported MMDVM_HS target. The live session used the exact AX25R4 firmware already installed by 0C-P2 and did not flash, reset, touch GPIO, write option bytes, or transmit RF.

## Frozen inputs

- starting project checkpoint: `ddd881b868f851cf955703e1e7d277d1537b76d9`
- staged-green checkpoint: `c9333b9e57101ed8c210030becde3265939d21b0`
- AX25R4 SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- receive frequency: 145.050 MHz
- RSSI polling: 50 ms
- P2 detector: BUSY `<=83`, CLEAR-release `>=90`, hysteresis `84..89`, 250 ms continuous-clear hold
- P1 CSMA: `PERSIST=63`, `SLOTTIME=10` = 100 ms, 30 s bounded wait
- qualification persistence source: explicit `255` before live BUSY, then post-busy `255,0`

## Physical sequence

The shadow access attempt started fail-closed. At elapsed 0.008 s, raw RSSI 106 produced detector `RECENT_RX` and P1 `WAIT_CLEAR`. After the 250 ms release hold, detector CLEAR was first observed at 0.300 s and P1 began a full clear slot.

The qualification intentionally supplied persistence byte 255 repeatedly before real RF arrived. Twenty-six due P1 slots were deferred without any transmit path being present or invoked.

At elapsed 3.652 s, the live channel produced raw RSSI 48. The qualified detector immediately entered `BUSY`, and P1 immediately returned to `WAIT_CLEAR`, canceling its prior clear-slot progression. This was the required live carrier-interruption proof.

After RF disappeared, detector `RECENT_RX` remained busy-for-access. At elapsed 4.701 s, detector CLEAR was observed and P1 began a brand-new full 100 ms slot. The first post-busy persistence trial occurred at 4.850 s, 149 ms after CLEAR, using explicit byte 255 and correctly deferring. The second post-busy trial occurred at 4.955 s, 105 ms later, using explicit byte 0 and producing `READY`.

`READY` was observational only. Nothing capable of transmitting was connected to it.

## Live AX.25 proof

The same bounded session independently decoded one FCS-valid AX.25 UI frame:

- source: `KJ6YWD`
- destination: `JIM`
- frame type: `UI`
- bytes excluding FCS: 61

This confirms the RSSI BUSY event occurred during real packet-channel activity rather than from a synthetic host observation.

## Counters and safety evidence

- RSSI samples: 100
- decoded AX.25 frames: 1
- packed RX bytes: 11965
- FIFO dropped bytes: 0
- pre-busy persistence deferrals: 26
- post-busy persistence trials: 2
- RF keyups: `0 -> 0`
- generated TX samples: `0 -> 0`
- single base `ModemOwner`: PASS
- KISS TX connected: NO
- TX broker connected: NO
- product TX enabled: NO
- RF transmitted: NO
- flash written: NO
- GPIO accessed: NO
- option bytes written: NO

## Qualified boundary

0C-P3 proves that live AX25R4 RSSI observations can safely drive the qualified P2 detector and unchanged P1 persistent-CSMA state machine end-to-end on real RF. A live BUSY observation cancels access eligibility; the 250 ms recent-RX hold remains busy-for-access; a later CLEAR observation starts a fresh complete 100 ms P1 slot; persistence byte 255 defers; and byte 0 can reach shadow READY only after the required timing.

This phase does **not** qualify transmission from READY. It does not connect `TXModemOwner`, `TXBroker`, KISS-originated TX, daemon TX, or persistent product TX. The next phase may connect a bounded queued transmit request to this already-qualified channel-access result in host-only/fail-closed form before any further over-air transmission is considered.

Exact machine-readable evidence is frozen in `firmware/qualification/0c-p3-live-shadow-channel-access-physical-evidence.json`.
