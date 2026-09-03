# 0C-P8 R3 guarded physical sustained KISS qualification

Date: 2026-09-03  
Frequency: 145.050 MHz  
RF power: 200/255  
Target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`  
Firmware: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

## Result

**PHYSICALLY QUALIFIED by R3.**

The exact physical execution used branch `dev-0c-p8-live-sustained-kiss-tnc-r3` at execution head `b301e9098aedf64e4eb9adf746b93a8f7a7482ac`, rooted in host-qualified P8 R1 checkpoint `checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified` / `e8d104b2c6a295219e34733d2541f89ee90318f3`.

R3 superseded the physically useful but qualification-invalid R2 run. R2 transmitted and externally decoded all three frames, but its raw-body self-echo classifier allowed C/H-bit-mutated qualification echoes to satisfy the fresh non-qualification RX gate. R3 replaced only that qualification classifier with semantic AX.25 identity: destination/source/path callsign+SSID, frame type, PID and information payload are compared while AX.25 C/H flag state is deliberately ignored.

## Physical sustained-session proof

A real localhost KISS listener remained active across the qualification. Exactly two TCP KISS client sessions were used, with the required disconnect/reconnect after cycle 1. Exactly three port-0 KISS DATA messages without FCS were admitted one at a time; the TNC appended FCS exactly once.

The three fixed R3 packets were:

- `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 1/3`
- `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 2/3`
- `KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 R3 SUSTAINED 3/3`

TXDELAY sequence was `30, 50, 30`; generated sample counts were exactly `12960, 16784, 12944`. PERSIST/SLOTTIME remained `63/10` and automatic retry remained disabled.

Every cycle required both real RF BUSY and a fresh FCS-valid non-qualification AX.25 decode before dispatch. Each then proved the deterministic qualification persistence sequence `255` defer followed by `0` dispatch and completed the real half-duplex lifecycle `RX_STOP -> TX -> RF idle -> RX_START`.

Cycle timing evidence:

| Cycle | Clear -> defer | Defer -> dispatch | Generated samples |
|---|---:|---:|---:|
| 1 | 0.314 s | 0.223 s | 12960 |
| 2 | 6.881 s | 0.175 s | 16784 |
| 3 | 15.424 s | 0.228 s | 12944 |

The long clear-to-defer intervals in cycles 2 and 3 are expected qualification wait time: the queue remained blocked until a genuine non-qualification decode arrived. Qualification echoes were observed first and were correctly excluded.

## Self-echo classifier proof

The live R3 log proves the R2 defect is closed:

- During cycle 2, the RF-heard R3 `1/3` qualification packet decoded with `fresh_non_p8=0`; only the later `KJ6YWD>JIM` packet armed fresh RX.
- During cycle 3, the RF-heard R3 `2/3` qualification packet decoded with `fresh_non_p8=0`; only the later `KJ6YWD>JIM` packet armed fresh RX.
- During the final queue-empty proof, the R3 `3/3` echo was received while no TX request was queued. The harness snapshots the global semantic non-qualification count after cycle 3 and requires that count to increase, so the echo cannot satisfy the final gate. The later genuine `KJ6YWD>JIM` packet advanced the count and was delivered through live KISS.

The dedicated C/H mutation regression also remains green: destination/source/path C/H bits are deliberately flipped to reproduce R2's raw-byte mismatch, and the mutated qualification frame still cannot arm `fresh_non_p8`; a genuine non-qualification frame can.

## Independent direct RF decode

An independent 1200-baud packet receiver decoded all three exact direct R3 transmissions:

- 15:25:21 local — R3 `1/3`
- 15:25:31 local — R3 `2/3`
- 15:25:48 local — R3 `3/3`

Operator-supplied screenshot SHA-256: `139c7c3be655677fd245653f50f35ca3d943598872f4e9e1587b21c22744b901` (`1017x261`).

`YWDNOD*` repeat proof remains intentionally deferred/non-blocking; the required direct-decode gate is satisfied 3/3.

## Final counters and safety boundary

- KISS TCP clients: 2
- KISS DATA admitted: 3
- TX submissions: 3
- complete RX/TX/RX cycles: 3
- RX starts: 4 total (1 initial + 3 post-TX)
- RX stops: 3
- post-TX Bell-202 decoder resets: 3
- genuine non-qualification FCS-valid inbound frames: 4
- RSSI samples: 172
- packed RX bytes drained: 112514
- RX read transactions: 593
- RX status checks: 115
- FIFO dropped bytes: 0
- queue clock serialization: PASS
- RX FIFO backlog priority: PASS
- single modem owner: PASS
- UART released: YES
- duplicate dispatch: NO
- automatic retry: NO
- product/daemon TX: DISABLED
- flash/GPIO/option-byte activity: NONE

The R3 manifest is now `physically-qualified`, `runnable=false`, and `qualification_complete=true`. Because R3 accepted three RF transmissions, the same stage must not be rerun. Its entrypoint is required to fail closed before `LIVE_RUNTIME=OPEN` or UART access.

Authoritative machine-readable evidence: `firmware/qualification/0c-p8-r3-live-physical-evidence.json`.
