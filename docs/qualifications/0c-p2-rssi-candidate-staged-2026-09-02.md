# 0C-P2 AX25R4 RSSI Candidate Staging — 2026-09-02

Status: **STAGED / CI-GREEN — FIRMWARE NOT BUILT ON TARGET, NOT FLASHED, NO CARRIER THRESHOLD SELECTED**

## Purpose

0C-P2 will provide the trustworthy live busy/clear observation source for the already host-qualified 0C-P1 p-persistent CSMA policy.

This staging step deliberately stops before choosing a carrier threshold. The exact MMDVM_HS Hat configuration already compiles the ADF7021 RSSI readback path, so P2 uses real radio RSSI telemetry rather than inferring channel occupancy from successfully decoded AX.25 frames.

## Physical boundary retained

The latest physical target remains:

`0b-p13b-known-packet-tx-qualified`

The exact qualified AX25R3 artifact remains unchanged:

- artifact: `firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`
- size: `59812`
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- identity: `MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

0C-P2 staging does not alter that artifact, its physical qualification, P12a/P12b evidence, or P13b TX evidence.

## Real RSSI source

Pinned upstream MMDVM_HS commit:

`7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`

The exact pinned `configs/MMDVM_HS_Hat.h` includes `SEND_RSSI_DATA`, and the ADF7021 implementation already contains `CIO::readRSSI()` using register-7 RSSI ADC readback through SREAD.

The firmware routine returns a raw `uint16` RSSI magnitude. 0C-P2 intentionally exposes that raw value first; it does **not** yet claim calibrated dBm or a DCD/carrier boolean.

## AX25R4 additive engineering transform

YWD-MMDVM engineering branch:

`dev-0c-p2-rssi`

Pinned engineering RSSI commit:

`69309644da839522102e393e66093378544869ea`

New transform:

`firmware/ax25-rx4/apply_ax25_rx4_rssi.py`

Pinned transform blob:

`f69382dc0dbdb5c9d04bf2b04ea197d2840e5e03`

The transform is layered strictly after the complete frozen AX25R3 chain. It adds one read-only host subcommand:

- namespace: `YWD_RX` / `0x59`
- RSSI subcommand: `0x05`
- request: `E0 04 59 05`
- response: `E0 06 59 05 <lo> <hi>`
- value: little-endian raw ADF7021 RSSI magnitude

The RSSI request is accepted only while passive AX.25 receive capture is active, the modem is in AX25 state, and both firmware TX states are idle. It is therefore read-only receive telemetry, not a new RF-control operation.

The existing YWD_RX STATUS layout remains revision `3` unchanged.

Engineering identity becomes:

`YWD-AX25R4-v0.2.3`

Product candidate identity is staged as:

`MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

## Deterministic candidate build

New build manifest:

`firmware/tooling/packet-rssi-build-manifest.json`

Profile:

`0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse`

The candidate build retains:

- upstream MMDVM_HS commit `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`
- STM32F10X_Lib `1debc23063f3942608e2bd62d04d5e1249c47fa3`
- STM32 HSE `8000000`
- ADF7021 TCXO `14745600`
- no OSC override
- all twelve frozen AX25R3 engineering blobs unchanged
- the one pinned AX25R4 RSSI transform as the thirteenth engineering file

The exact upstream source pins include:

- HAT config blob `1c526b41dd96ea68823f2e83442a8a76fd59590a`
- upstream version blob `4239a854ec09ee90847468f931e1455ee461e2de`
- Makefile blob `c73834e9734e4b74bd375cb98ce5144c31134de6`
- `scripts/build_fw.sh` blob `30257c0aea66695ed32877b8688daa835ee4f0e2`

Builder:

`firmware/build-packet-rssi-ywd1278.py`

The default build performs two independent builds and requires byte-for-byte equality. It is build-only: no modem device, GPIO, `stm32flash`, `sudo`, RF configuration, or RF transmission path exists in the builder.

No target artifact size or SHA256 is recorded yet because the candidate has intentionally **not yet been built on the target Pi**.

## Host telemetry boundary

`src/ywd1278/modem/protocol.py` adds the typed `RX_RSSI = 0x05` codec and returns `RXRSSI(raw_magnitude=...)`.

`src/ywd1278/modem/owner.py` adds `rx_rssi()` through the existing single UART-owner thread. The base `ModemOwner` still has no selector-burst TX method, no raw public transact, and no RF TX API.

The TCP KISS server and product daemon remain completely disconnected from RSSI-driven TX, the TX broker, and the CSMA policy.

## CI evidence

Corrected staging head before this documentation:

`f50542af087917a14d7cc8de9f4796752bf88f8b`

GitHub Actions:

- workflow: `framework-ci`
- run: `33694635918`
- run number: `286`
- conclusion: **success**

The run passed, among all historical gates:

- deterministic 0C-P1 CSMA policy regression
- deterministic 0C-P1 CSMA architecture contract
- RSSI telemetry host regression
- AX25R4 RSSI firmware build contract
- original P13b one-shot contract
- historical P13b-R1 contract
- qualified P13b-R2 contract
- P12a/P12b physical-evidence contracts
- package installation
- framework self-test

No CI step accesses hardware or transmits RF.

## What is not yet qualified

0C-P2 is still incomplete. Specifically, this staging does **not** prove:

- the AX25R4 artifact builds reproducibly on the target Pi
- the AX25R4 artifact can be safely activated on the physical HAT
- the new product identity runs correctly on the HAT
- RSSI values distinguish idle-channel noise from real received signals
- signal-strength direction/magnitude on this exact HAT
- a carrier threshold
- hysteresis
- recent-RX hold behavior
- live integration into 0C-P1
- KISS-originated TX
- persistent product TX

## Next gate

The immediate next action is **build-only** on the Pi. The build must produce two byte-identical AX25R4 binaries and a locked artifact size/SHA256 before any flash/activation harness is designed.

Only after the exact artifact is recorded and CI-green will a separate guarded physical receive-only activation/telemetry test be staged. That later test will collect real RSSI samples during idle RF and independently generated received traffic before any carrier threshold is selected.
