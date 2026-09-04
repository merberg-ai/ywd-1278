# Fresh-install Stage B — production `ywd1278d` host qualification

Date: 2026-09-03 (America/Los_Angeles)

## Result

**HOST QUALIFIED.** Stage B replaces the original fail-closed product daemon stub with a real appliance packet-engine lifecycle assembled entirely by composition around the frozen Stage-A packet-engine boundary.

No Stage-A packet-engine source blob was modified. No physical UART, RF, flash, GPIO/reset, or option-byte operation was performed by Stage B qualification.

## Frozen base

- Stage-A checkpoint: `checkpoint/product-packet-engine-stage-a-qualified`
- Stage-A checkpoint SHA: `704814a7c68099ca6bc7aef041d531014cb47d78`
- Frozen Stage-A component count: 29
- Stage-A manifest: `firmware/qualification/0b-product-packet-engine-stage-a.json`
- Stage-A manifest blob: `d7eaa4c24bd4fa8f9066403153be534a3d40a81b`

## Qualified implementation

- Qualified implementation head: `8cf916e1f44c201be5261d08f611ab8e8b638296`
- Dedicated successful CI run: `33839528014`
- Appliance composition module: `src/ywd1278/service/appliance.py`
- Appliance blob: `6d8c232c8927e9c76306c34779c1ce0da92ec010`
- Product daemon: `src/ywd1278/daemon.py`
- Daemon blob: `f080abda1792577269b11833deec45edd4e95535`
- Regression suite: `tests/product_daemon_stage_b_test.py`
- Regression blob: `e2fbb352fa98c6c0c3545dca0ecfd11348069ecc`
- Stage-B contract: `tests/product_daemon_stage_b_contract_test.py`
- Contract blob: `5c87804fe18e2b954392228003b66c25ba0179e8`

The evidence-bearing Stage-B manifest was subsequently validated at head `4b8dde29a9c52fb34ab01a6de951c5b14558095f` by CI run `33839587334`, which also completed successfully.

## Product runtime graph

The Stage-B appliance layer owns lifecycle/configuration only and composes the frozen qualified graph:

1. one `TXModemOwner` owns the modem transport;
2. exact AX25R4 firmware identity is required;
3. RF-idle status is verified before configuration;
4. packet RX is configured and started;
5. `ContextualTXDelayRouter`, `ContextualHalfDuplexSubmitter`, and the bounded thread-safe DATA admission queue are composed;
6. `SustainedTNCRuntime` owns sustained RX/Bell-202/AX.25/channel-access scheduling;
7. the KISS listener is exposed only after the sustained runtime passes its initial identity/RX-active gate;
8. shutdown closes KISS ingress first, then runtime, TX router, RX state, and finally the single modem owner.

`ywd1278d` now installs SIGINT/SIGTERM handlers that request graceful shutdown through a stop event. Expected product configuration/runtime failures terminate through the controlled exit-78 path after cleanup rather than leaving an uncontrolled traceback as the normal service contract.

## Safe TX-disabled product mode

The normal product-safe state remains TX disabled.

When `radio.tx_enabled = false`:

- inbound port-0 KISS DATA is rejected immediately at the ingress/control boundary;
- the bounded TX admission queue remains empty;
- no downstream TX broker is permitted to transmit;
- RX/Bell-202/AX.25/KISS service remains healthy and operational.

The host regression injects a complete Bell-202 capture through a thread-bound fake AX25R4 modem and proves the frame is decoded and delivered through a real localhost KISS connection while a client-originated DATA frame is rejected and no fake TX occurs.

## Guarded TX-enabled composition

Stage B does **not** introduce arbitrary product TX configuration. If TX is enabled, construction is accepted only for the already physically-qualified profile:

- frequency: `145050000` Hz;
- power byte: `200`;
- exact AX25R4 product identity required.

On the host fake modem, one KISS DATA frame traverses the real frozen KISS admission, CSMA, contextual TXDELAY, half-duplex RX_STOP -> TX -> RF-idle -> RX_START path. The fake endpoint records exactly one accepted selector burst and RX restart. This is composition qualification only; Stage B did not transmit RF.

## Configuration fail-closed behavior

Host tests reject, before product operation:

- missing/unknown HAT target;
- unconfigured frequency;
- TX enabled on any frequency other than 145.050 MHz;
- TX enabled with any power other than 200;
- non-loopback Stage-B KISS bind;
- automatic firmware flashing;
- beaconing before 0F qualification.

The existing example configuration and systemd unit remain unchanged/frozen in this stage.

## Regression result

`tests/product_daemon_stage_b_test.py` passes 4/4 tests:

1. fail-closed configuration matrix;
2. healthy RX-only + KISS DATA rejection + Bell-202/AX.25/KISS delivery;
3. guarded TX-enabled full frozen graph on the fake thread-bound modem with RX restart;
4. `run_daemon()` stop-event lifecycle with clean single-owner release.

## Historical P8 contract boundary

The first Stage-B CI layering run (`33839344279`) failed only because the immutable historical P8 architecture contract intentionally pinned the pre-Stage-B `daemon.py` stub blob. Before that assertion, the new Stage-B regression/contract, Stage-A freeze, P8 concurrency test, and P8 sustained integration test had all passed.

The historical P8 contract was **not rewritten**. Stage B preserves its exact blob `fa49c652cb2ca86c01a1e9c4c2244d30c4c6b83e`, records that its daemon-stub assertion is superseded by the product-daemon stage, and separately replays the actual P8 behavioral tests plus the frozen P7/P8 physical-evidence contracts.

## Evidence scope

This Stage-B qualification proves host-side product composition only. It does **not** prove:

- installed-package/systemd operation on the Pi;
- physical POSIX-UART operation through the new product daemon;
- product-daemon RF TX;
- firmware installation/flashing from the installer;
- monitor/logging/MHEARD/diagnostics composition;
- classic console composition;
- reboot persistence;
- fresh Raspberry Pi OS installation.

Those remain later gates in issue #35.

## Next gate

Compose the already-qualified 0D monitor/logging/MHEARD/diagnostics path into this Stage-B product daemon while preserving the frozen packet-engine boundary and the Stage-B lifecycle contract.
