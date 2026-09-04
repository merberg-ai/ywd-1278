# Fresh-install Stage F — firmware trust/deployment host qualification

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage F is **host-qualified; physical existing-Pi rehearsal is still pending**.

Qualified implementation anchor:

- branch: `dev-fresh-install-stage-f-firmware-trust`
- implementation SHA: `3a976d6209752411b3a2823db6ffcc6ce341fd6a`
- dedicated CI: `33878913819` — success
- base checkpoint: `checkpoint/product-installer-runtime-stage-e-host-qualified` @ `73891a37c2d7de19aebb1f55bdd0324b121bbf02`

## Product firmware anchor

The product deployment profile names only the already physically qualified AX25R4 image:

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- size: `59892` bytes
- SHA256: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`
- exact runtime identity: `MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`
- physical anchor: 0C-P2 at 145.050 MHz

The exact image is prepared by the frozen deterministic AX25R4 build lineage. `firmware/out/` remains build output rather than an unverified checked-in binary.

## Protected rollback gate

Before any product write can occur, Stage F requires a target-bound stock rollback backup with:

- full main-flash size `131072` bytes;
- two independent byte-identical reads;
- exact stock SHA256 `4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684`;
- no option-byte read/write;
- backup manifest and image consistency.

If the HAT is currently exact allowlisted stock, the existing frozen `firmware/flash.sh backup` path captures a fresh protected backup. If it is already running YWD firmware, a previously captured verified stock backup must be supplied or found.

## Explicit write authorization

A main-flash write is reachable only when all static/runtime safety gates pass and the operator supplies:

- `--authorize FLASH-QUALIFIED-AX25R4`
- the final interactive phrase `WRITE-FIRMWARE-NOW`

Unknown/ambiguous HAT identity fails closed. The deployment script refuses to steal a busy UART from an unknown owner.

## Programmed readback and runtime identity

After a write, Stage F independently reads back exactly the programmed `59892` bytes from `0x08000000` and requires the same AX25R4 SHA256 before restarting the application. It then requires the exact runtime identity above.

If that exact AX25R4 identity is already running, Stage F skips the write entirely and performs the same bootloader readback/hash verification plus exact runtime identity verification. This is the expected path for the current development Pi if its previously qualified AX25R4 installation is still intact.

## Service eligibility — not activation

Only after all of the following agree:

1. Stage-E runtime readiness is `READY`;
2. RF TX remains disabled;
3. automatic flash remains disabled;
4. exact target is known;
5. exact artifact hash passes;
6. verified stock rollback backup passes;
7. programmed readback hash passes;
8. exact AX25R4 runtime identity passes;

may `/var/lib/ywd-1278/firmware-ready.json` be written as `SERVICE-ELIGIBLE` evidence.

Stage F still does **not** enable or start `ywd-1278.service`.

## Host qualification coverage

CI `33878913819` passed:

- six Stage-F trust regressions;
- Stage-F architecture/safety contract;
- packaged `pip install .` trust-module smoke;
- Stage-E installer/runtime regressions and architecture preservation;
- Stage-D full daemon graph and architecture preservation;
- Stage-C observability preservation;
- Stage-A packet-engine freeze;
- sustained TNC and physical-evidence contracts;
- zero-I/O daemon framework self-test.

No UART, RF, GPIO, bootloader, flash, option-byte, or service-start operation occurred during this host qualification.

## Next step

Perform the **existing-Pi installed-appliance rehearsal with TX disabled**. Install the candidate, prepare/verify the exact AX25R4 artifact, verify the existing stock rollback evidence, run Stage F against the real HAT (prefer readback-only if exact AX25R4 is already installed), establish service eligibility, then qualify systemd lifecycle and live RX/console operation before any physical TX subtest.
