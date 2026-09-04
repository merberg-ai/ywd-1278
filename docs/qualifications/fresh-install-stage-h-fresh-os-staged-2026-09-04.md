# Fresh-install Stage H — fresh Raspberry Pi OS qualification staged

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage H is **host-staged and ready for fresh Raspberry Pi OS physical qualification**. No fresh-OS physical claim is made yet.

Base checkpoint:

- `checkpoint/product-existing-pi-stage-g-qualified` @ `1e2ecb162fdd900ca80b8e69ca085f8d591e7aab`

Staging branch:

- `dev-fresh-install-stage-h-fresh-os`

Initial Stage-H CI anchor:

- implementation head `15c389d8df6a84a7adee5a93f6945f2852909fe2`
- run `33923952309` — success

## Physical qualification sequence

1. Clone the pinned Stage-H branch into `~/ywd-1278` on a freshly imaged Raspberry Pi OS target.
2. Run `tools/stage_h_fresh_os_preflight.sh` before any YWD-1278 installation.
3. Require `/opt/ywd-1278`, `/etc/ywd-1278`, `/var/lib/ywd-1278`, `/var/log/ywd-1278`, and YWD-1278 systemd units to be absent before install.
4. Capture Pi model, OS, kernel, architecture, kernel boot ID, UART audit, and pre-install HAT identity if the UART is immediately available.
5. Run the normal installer with callsign/frequency configuration and TX/automatic flash disabled.
6. If Raspberry Pi UART repair is required, use only the qualified installer repair + reboot + automatic resume path and prove resume success.
7. Prepare the exact qualified AX25R4 artifact and require SHA256 `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616` and size 59892.
8. Establish protected stock-backup/programmed-readback/runtime-identity evidence through the guarded firmware trust path. A real firmware write is permitted only if the HAT is not already the exact product image and only after all Stage-F safeguards pass.
9. Enable the product service only through the guarded service-activation gate.
10. Prove installed live RX at 145.050 MHz reaches KISS plus monitor/MHEARD and classic console surfaces with TX still disabled.
11. Prove reboot survival and fresh post-reboot RX.

## Safety boundary

The Stage-H preflight is read-only. It may inspect the UART and issue a read-only HAT identity probe only when the UART is already usable. It contains no platform repair, systemd service enable/start, reboot, programmer, firmware write, KISS DATA send, or RF TX capability.

The normal installer may perform the already-qualified Raspberry Pi UART repair and arm the install-resume service, but it still leaves `ywd-1278.service` disabled. Firmware deployment and service activation remain separate guarded stages. Physical TX remains explicitly prohibited during Stage H.
