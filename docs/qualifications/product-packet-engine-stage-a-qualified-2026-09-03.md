# Stage A — first product packet-engine component freeze

Date: 2026-09-03 (America/Los_Angeles)

Status: **qualified**

This stage freezes the exact already-qualified packet-engine component graph that the fresh-install appliance work may compose into `ywd1278d`. Stage A does not change any packet-engine source, open the UART, access RF, write firmware, manipulate GPIO, enable the daemon, or enable product TX.

## Frozen baseline

- Pre-appliance checkpoint: `checkpoint/pre-fresh-install-flash-run`
- Baseline SHA: `383de08ede7b452fc773bc5cb6803e4a5acd39cf`
- Working branch: `dev-fresh-install-flash-run`
- Stage A qualified implementation/evidence head: `f1d7584be28fc96eee956be20fcc3b7a32e02b44`
- Dedicated CI run: `33838613305` — **success**

The authoritative blob list is `firmware/qualification/0b-product-packet-engine-stage-a.json`. It contains exactly 29 source blobs across AX.25, Bell-202, modem ownership/protocol/configuration, KISS framing/control/ingress/sustained service, CSMA/channel detection/TX lifecycle, and the P8 sustained TNC scheduler.

Package `__init__.py` blobs are included because changing an exported symbol can alter composition behavior even if an implementation module itself is unchanged.

## Product graph frozen for Stage B

1. POSIX serial transport -> one `TXModemOwner`.
2. `TXModemOwner` -> AX25R4 `YWD_RX` FIFO plus typed RSSI/RF diagnostics.
3. Packed RX samples -> streaming Bell-202 -> AX.25 -> KISS `PacketEvent`.
4. KISS TCP/control -> immutable parameter capture -> bounded P7 DATA admission.
5. Queued DATA -> qualified RSSI detector + p-persistent CSMA -> exactly-once READY dispatch.
6. READY -> contextual P4e `RX_STOP -> TX -> RF-idle -> RX_START` lifecycle.
7. Captured TXDELAY -> contextual `TXDelayBroker` -> Bell-202 selector burst -> single modem owner.
8. P8 sustained scheduler resets Bell-202 decoder state after each half-duplex TX discontinuity.

Historical/analysis-only helpers intentionally excluded from the first product graph are:

- `src/ywd1278/tx/access_queue.py`
- `src/ywd1278/tx/rssi_analysis.py`
- `src/ywd1278/service/live_channel_access.py`
- `src/ywd1278/service/rx_runtime.py`

They remain preserved in repository history and existing qualification gates; exclusion here does not invalidate their historical evidence.

## Firmware anchor

The first appliance qualification remains tied to the physically-qualified AX25R4 firmware:

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- size: `59892` bytes
- SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- programmed readback SHA256: same exact SHA
- first fresh-appliance RF qualification frequency: `145.050 MHz`
- physically-qualified TX power for the acceptance test: `200/255`

Stage A does **not** flash this firmware; it only freezes the already-existing proof anchor.

## Replayed qualification

Dedicated Stage A CI replayed and passed:

- exact 29-component and proof-blob hash contract;
- P8 concurrent bounded KISS admission;
- P8 sustained localhost KISS full graph;
- P8 architecture/safety contract;
- P7 bounded KISS DATA admission and full fake-hardware graph;
- P6 KISS controls;
- P4e persistent half-duplex lifecycle;
- P5 TXDELAY policy;
- frozen P7 one-shot physical-evidence contract;
- frozen P8 R3 physical-evidence contract.

The frozen P8 R3 evidence remains the end-to-end physical proof: three KISS-originated transmissions, three complete RX/TX/RX cycles, 3/3 independent external direct decodes, zero FIFO drops, no duplicate dispatch, no automatic TX retry, and clean UART release at 145.050 MHz.

## Safety and scope

Stage A performed no physical test because none was required. No packet-engine component changed, and all physical claims are inherited only from already-frozen evidence.

The production daemon is still not assembled by this stage. Installer flash integration, installed-appliance rehearsal, and the fresh Raspberry Pi OS qualification remain open.

Next: **Stage B — assemble the production `ywd1278d` graph around these frozen components.**
