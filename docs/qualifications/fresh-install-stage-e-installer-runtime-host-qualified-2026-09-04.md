# Fresh-install Stage E installer/runtime integration — host qualified

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage E is host-qualified for installer/runtime integration.

Qualified implementation head:

`68f52d6432c3d9580a9f5ecf7a3fe84f4d07d6d8`

Exact-head GitHub Actions run:

`33876037818` — `success`

This stage updates the normal Raspberry Pi installer and reboot-resume path around the already-qualified Stage-D product daemon. It does **not** add firmware-write authority and it does **not** enable or start `ywd-1278.service`.

## What changed

- Added packaged zero-I/O runtime readiness checker:
  - `python -m ywd1278.install.readiness --config PATH`
  - `READY` / exit 0
  - safely `INCOMPLETE` / exit 10
  - `UNSAFE` / exit 20
- `installer/setup.sh` now emits the Stage-D product PTY profile:
  - `pty_enabled = true`
  - `pty_link = "/run/ywd-1278/tnc"`
- Setup still writes:
  - `radio.tx_enabled = false`
  - `firmware.allow_automatic_flash = false`
- `installer/install.sh` runs the readiness gate after setup.
- `installer/resume.sh` runs the same readiness gate after post-reboot HAT target binding.
- Unsafe/invalid configuration stops installation and leaves the packet service disabled.
- Safely incomplete configuration may finish installation but remains disabled.
- Even a READY configuration remains disabled pending the later firmware-verification/service-enable gate.

## Readiness meaning

`READY` proves configuration coherence only. It requires the product station identity, supported HAT target, configured radio frequency, loopback-qualified KISS policy, monitor/MHEARD logging, qualified classic console policy, and the product PTY path.

It explicitly rejects or fails closed on unsafe configuration including TX enabled, automatic firmware flash enabled, unsupported hardware target, malformed/public console policy, non-product PTY path, and KISS/console port collision.

When authenticated RFC1918 Telnet is configured, the protected auth file must exist and pass the frozen P3 credential-file validation before readiness can become READY.

`READY` does **not** prove that the attached HAT contains the qualified AX25R4 firmware. That trust decision belongs to the next stage.

## Host qualification

The Stage-E CI run proved:

- Python compilation of the packaged readiness module and Stage-E tests;
- `bash -n` success for `installer/install.sh`, `installer/setup.sh`, and `installer/resume.sh`;
- safe shipped example configuration is INCOMPLETE, not unsafe;
- complete product configuration reaches READY without modem/socket hardware I/O;
- TX-enabled configuration is UNSAFE;
- auto-flash-enabled configuration is UNSAFE;
- public/wildcard console configuration is UNSAFE;
- missing required private-LAN auth material remains INCOMPLETE;
- KISS/console port collision is UNSAFE;
- a fresh temporary venv can `pip install .` and run the packaged readiness module;
- packaged `ywd1278d --framework-self-test` remains zero-I/O;
- Stage-D Telnet/PTTY/live-MHEARD integration still passes;
- the Stage-D simultaneous full daemon graph still passes;
- Stage-C observability behavior remains green;
- the Stage-A packet-engine freeze remains exact;
- frozen 0D/0E and sustained-TNC physical evidence contracts remain green.

## Frozen boundaries

Stage E leaves the following qualified boundaries unchanged:

- Stage-D product packet engine/observability/classic-console composition;
- production `ywd1278d` daemon;
- product systemd service units;
- shipped safe example configuration;
- hardware detection and Raspberry Pi UART platform-repair helpers;
- existing physical modem/RF qualification evidence.

## Hardware activity

Host qualification performed no:

- modem UART access;
- RF receive/transmit test;
- firmware flash;
- GPIO/reset operation;
- option-byte operation;
- product service start.

## Still not qualified

Stage E does not qualify:

- protected stock-firmware backup during the normal installer;
- the exact AX25R4 firmware write;
- post-flash readback verification;
- runtime product identity verification after flash;
- enabling/starting `ywd-1278.service` after firmware verification;
- installed-appliance lifecycle on the physical Pi;
- fresh Raspberry Pi OS acceptance;
- new live RF or physical TX evidence.

## Next stage

Add the guarded firmware-deployment gate in this strict order:

1. supported platform/HAT identification;
2. protected stock firmware backup and verification;
3. exact allowlisted AX25R4 artifact selection;
4. explicit guarded flash authorization;
5. flash;
6. programmed readback verification;
7. exact runtime/product identity verification;
8. preserve rollback material;
9. only then make service-enable eligibility possible.

Unknown or ambiguous hardware/firmware must remain fail-closed throughout.
