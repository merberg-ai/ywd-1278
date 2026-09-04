# Fresh-install Stage G — existing-Pi installed-appliance rehearsal staging

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage G is **host-staged and ready for the first installed-appliance physical rehearsal**. No Stage-G physical claim is made yet.

Host staging anchor:

- base: `checkpoint/product-firmware-trust-stage-f-host-qualified` @ `5473ed29580d98555d81e4a02d663a57bc373bd8`
- staging branch: `dev-fresh-install-stage-g-existing-pi`
- host implementation SHA: `967a05eaf2170a1cb4d6d46748798985d33d4dc6`
- dedicated CI: `33881826222` — success

The host gate passed the Stage-G RX helper regression and architecture/safety contract and replayed the frozen Stage-F firmware trust chain, Stage-E installer runtime, Stage-D full daemon graph, Stage-A packet-engine freeze, sustained TNC physical-evidence contracts, and the zero-I/O daemon framework self-test.

## Scope

The physical rehearsal is RX-only and uses the existing Raspberry Pi/HAT installation before any fresh-OS wipe.

It must prove:

1. the exact Stage-G candidate installs through the normal installer;
2. runtime setup is 145.050 MHz with RF TX disabled and automatic flash disabled;
3. the exact AX25R4 artifact is prepared and hash-verified;
4. Stage F establishes real stock-rollback + programmed-readback + runtime-identity evidence;
5. if exact AX25R4 is already installed, no main-flash rewrite occurs;
6. service activation is impossible until the Stage-F `SERVICE-ELIGIBLE` record revalidates;
7. live HAT identity is rechecked immediately before service activation;
8. systemd stop/start/restart and SIGTERM cleanup release the UART and PTY correctly;
9. one known packet on 145.050 MHz reaches the installed TCP KISS port;
10. the decoded AX.25 source appears in both Telnet and PTY `MHEARD` views.

## Stage-G service activation boundary

`installer/enable-product-service.sh` is the first product gate allowed to execute `systemctl enable --now ywd-1278.service`.

It requires, before that action:

- exact `/opt/ywd-1278/installed-commit` supplied by the operator;
- installed systemd unit identical to installed source;
- Stage-E runtime readiness still valid;
- Stage-F `SERVICE-ELIGIBLE` evidence still valid;
- TX disabled;
- automatic flash disabled;
- 145.050 MHz configuration;
- exact supported target;
- exact live AX25R4 runtime identity;
- free UART prior to service start.

The Stage-G service activation script contains no programmer/bootloader/write path.

## RX-only qualifier

`tools/qualify_stage_g_systemd_rx.sh` exercises:

- `systemctl stop` and graceful SIGTERM cleanup;
- PTY removal and UART release after stop;
- `systemctl start` and PTY recreation;
- `systemctl restart` with a new daemon PID;
- loopback KISS and Telnet reachability;
- `tools/qualify_stage_g_live_rx.py` for one live KISS DATA receive and MHEARD correlation.

The live-RX helper never opens the modem UART and its KISS receive function has no send operation. Console writes are limited to read-only/status-oriented classic commands such as `HEALTH` and `MHEARD`.

## Explicitly deferred

This Stage-G run does **not** qualify:

- reboot survival — performed as a separate follow-up after the first live RX pass;
- KISS DATA transmit;
- any RF TX;
- 0F UNPROTO/converse/beaconing;
- 0G connected mode;
- fresh Raspberry Pi OS installation.

## Physical stopping rule

Any mismatch in installed commit, runtime readiness, firmware artifact, stock rollback evidence, programmed readback, exact AX25R4 identity, UART ownership, service state, PTY lifecycle, or live RX causes the rehearsal to stop. Do not bypass a failed gate and do not proceed to TX.
