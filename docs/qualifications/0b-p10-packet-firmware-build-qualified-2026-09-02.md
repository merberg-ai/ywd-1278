# 0B-P10 — Deterministic packet firmware build qualification

Date: 2026-09-02

Status: **QUALIFIED — BUILD/ARTIFACT ONLY**

This qualification establishes the deterministic YWD-1278 product build of the already physically qualified AX25R3 engineering firmware lineage. It does **not** qualify this product-branded artifact as runnable on the STM32 yet. No HAT, UART, GPIO, RF, or flash operation was used by this phase.

## Code under test

- Repository: `merberg-ai/ywd-1278`
- Branch used on target Pi: `dev`
- Commit: `4ab10b819f9b4775cdd7e7a6c66d62db1b7fa050`
- Builder entry point: `bash firmware/build-packet-ywd1278-frozen.sh`

## Frozen source lineage

- Upstream MMDVM_HS commit: `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`
- STM32F10X_Lib commit: `1debc23063f3942608e2bd62d04d5e1249c47fa3`
- Frozen YWD-MMDVM engineering commit: `d25180ad663d781b761c525d1e699e7b052d6214`
- Engineering source acquisition: exact frozen commit fetched from Git into a temporary object store; no engineering checkout/worktree was created or trusted.
- Frozen engineering transform/support files verified: 12

Applied deterministic transform order:

1. `firmware/stage4/apply_stage4.py`
2. `firmware/ax25-classic1/apply_ax25_classic1.py`
3. `firmware/ax25-classic1/apply_ax25_classic1_diag.py`
4. `firmware/ax25-classic1/apply_ax25_classic1_continuity.py`
5. `firmware/ax25-classic1/apply_ax25_classic1_reserve.py`
6. `firmware/ax25-rx1/apply_ax25_rx1.py`
7. `firmware/ax25-rx2/apply_ax25_rx2.py`
8. `firmware/ax25-rx3/apply_ax25_rx3.py`
9. YWD-1278 product branding only

The product branding gate reported:

- `FROZEN_AX25R3_BEHAVIOR_ANCHORS=PASS`
- `BEHAVIORAL_CHANGES_AFTER_FROZEN_AX25R3=NONE`

## Clock/build invariants

- STM32 HSE: `8000000` Hz
- ADF7021 TCXO: `14745600` Hz
- `OSC` override: **NO**
- Upstream HAT build recipe gate: **PASS**
- Toolchain: `arm-none-eabi-gcc (15:14.2.rel1-1) 14.2.1 20241119`
- GNU Make: `4.4.1`
- `SOURCE_DATE_EPOCH=1696532075`

## Qualified artifact

Artifact path on the target Pi:

`firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin`

Exact properties:

- Size: `59812` bytes
- SHA256: `a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`
- Initial SP: `0x20005000`
- Reset vector: `0x08008061`
- Identity occurrence count in artifact: `1`

Expected runtime identity for the later physical gate:

`MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Packet info token:

`YWD-1278-AX25R3`

## Reproducibility evidence

Independent clean build A:

`a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`

Independent clean build B:

`a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310`

Result:

- `REPRODUCIBILITY=PASS`
- `ATOMIC_PUBLISH=PASS`

## Safety evidence

The build reported:

- `HARDWARE_ACCESSED=NO`
- `MODEM_UART_OPENED=NO`
- `RF_TRANSMITTED=NO`
- `FLASH_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

The artifact contains the previously qualified AX25 RX/TX firmware behavior, but the **build process** exposes no hardware or RF path.

## Qualification boundary

0B-P10 qualifies only:

- exact frozen source lineage;
- exact transform order and object hashes;
- correct STM32/ADF7021 clock separation;
- deterministic product branding;
- byte-for-byte reproducibility;
- exact artifact size/hash/identity.

0B-P10 does **not** yet claim that this new product-branded packet image boots on the target STM32. A separate guarded write/readback/runtime-identity/exact-stock-restore round trip is required before the packet firmware may be treated as a physically qualified running image.
