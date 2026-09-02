# YWD-1278 0A Framework Qualification — 2026-09-01

Status: **QUALIFIED — FRAMEWORK ONLY**

This checkpoint does not qualify packet RF, firmware flashing, or the installer on physical hardware. It qualifies the initial product repository/framework as internally consistent and fail-closed before the proven packet engine is ported.

## Tested code head

- branch: `dev`
- code head tested by CI: `beb5cbe7190c97d5ac140fea3f7c7ed775fa8077`
- workflow: `framework-ci`
- workflow run: `33591310800`
- result: `success`

## CI gates passed

- shell syntax for installer/firmware `.sh` files
- Python compilation for `src/` and `firmware/`
- JSON target-manifest parse
- TOML example-config parse
- clean Python virtual-environment package install
- `ywd1278 --version`
- fail-closed daemon framework self-test

The self-test intentionally opens no modem UART and transmits no RF.

## Framework present

- polished `main` landing README
- active `dev` branch
- Python package/version skeleton
- safe example TOML configuration with TX disabled
- colorized shared installer UI
- install/setup/uninstall scripts
- disabled-by-default systemd unit
- read-only MMDVM `GET_VERSION` identity probe
- firmware target allowlist
- fail-closed firmware flash framework
- protected firmware-backup metadata/checksum design
- stock restore workflow that accepts only target-bound stock identities
- explicit no-option-byte policy
- YWD-MMDVM qualified-code porting manifest
- product architecture and roadmap documentation

## Firmware state

The initial reference HAT target is intentionally:

- `status = reference-only`
- `flash_enabled = false`
- `flash_size_bytes = 0`
- no product firmware artifact
- no product firmware SHA256

Therefore the current product flash write path cannot pass its gates. This is intentional.

Before `flash_enabled` may become true, YWD-1278 must establish exact target geometry, deterministic product-branded firmware, artifact hash, rollback backup requirements, and physical requalification.

## Qualification boundary

The next development phase is **0B — Qualified Packet Engine Port**.

The source of truth is the frozen YWD-MMDVM packet-node foundation:

- `merberg-ai/ywd-mmdvm`
- `checkpoint/ax25-bidirectional-tnc-foundation`
- evidence commit `d25180ad663d781b761c525d1e699e7b052d6214`

No new RF behavior should be invented during the initial port. First reproduce the already-qualified Bell-202 RX/TX/KISS behavior under YWD-1278 structure/branding, then freeze a product requalification checkpoint.
