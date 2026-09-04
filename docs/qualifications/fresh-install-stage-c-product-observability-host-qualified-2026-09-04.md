# Fresh-install Stage C product observability — host qualified

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage C is host-qualified for composition of the already-qualified 0D observability stack into the production YWD-1278 packet-engine lifecycle.

Qualification implementation head:

`e45aef3326ed44241e6719f14e0b186acd0a07ee`

Dedicated GitHub Actions run:

`33870810415` — **SUCCESS**

Base checkpoint:

`checkpoint/product-daemon-stage-b-host-qualified` @ `f223737a001410d0ebeac221fd43722670c7ee03`

## What Stage C composes

The Stage-B product packet engine still owns the single modem/runtime graph. Stage C adds observation around the existing bounded `PacketEvent` backend:

```text
single TXModemOwner
  -> active AX25R4 RX
  -> sustained Bell-202 / AX.25 runtime
  -> bounded PacketEvent backend
       -> localhost KISS
       -> decoded monitor subscriptions
       -> optional SQLite live-frame logger
            -> read-only MHEARD queries
       -> one-shot diagnostics/status aggregation
```

No second modem owner, decoder, or packet queue was added.

The SQLite logger registers its existing bounded subscriber before the RX runtime starts, preventing an initial live decoded packet from falling through a composition gap. Shutdown stops the KISS listener and RX runtime before stopping the logger, so packet production ends before logger teardown.

## Configuration

Stage C uses the already-existing configuration keys:

- `[monitor].enabled`
- `[monitor].log_frames`
- `[storage].database`

The frozen example configuration and systemd candidate were not changed.

For Stage-B compatibility, absence of `[monitor]` means observability is disabled. If frame logging is requested, monitoring must be enabled and the database path must be absolute.

The typed `ProductPacketEngineConfig` is revalidated again at the capability-owning `ProductPacketEngine` constructor, so direct callers cannot bypass the qualified TX profile or other product configuration invariants by skipping the TOML loader.

## Host integration proof

The Stage-C regression uses the existing thread-bound in-memory AX25R4 fake modem. One synthesized Bell-202 AX.25 packet is injected into the real sustained product RX runtime and must be observed through all configured product surfaces:

1. TCP KISS receives the exact no-FCS AX.25 body.
2. The decoded monitor subscription returns the matching live TNC2-style record.
3. The frozen 0D SQLite logger persists exactly one live frame row.
4. The frozen read-only MHEARD view reports `KJ6YWD-10` with the expected destination/path/count.
5. One-shot diagnostics reports healthy runtime/backend/logger/MHEARD state.

The same running graph also proves Stage-B no-TX behavior remains intact: inbound KISS DATA is rejected at ingress, the TX admission queue stays empty, and the fake modem records zero accepted TX bursts.

A separate monitor-only test proves `monitor.enabled=true` with `log_frames=false` provides decoded monitor/diagnostics without creating a database or MHEARD writer.

A logger-startup-failure test proves startup fails closed and still releases the single modem owner on the owner thread.

## Preservation proof

The dedicated Stage-C gate passed all of the following on the same qualification head:

- Stage-C integration regression
- Stage-C architecture/safety contract
- exact Stage-A 29-component packet-engine freeze
- Stage-B behavioral regression
- frozen 0D monitor stream and monitor-policy tests/contracts/evidence
- frozen 0D SQLite logging tests/contracts/evidence
- frozen 0D MHEARD tests/contracts/evidence
- frozen explicit-only retention tests/contracts/evidence
- frozen 0D diagnostics tests/contracts/evidence
- sustained KISS concurrency/full-graph behavior
- P7/P8 physical evidence contracts without hardware access
- zero-I/O daemon framework self-test
- Stage-C manifest parse

All seven frozen `src/ywd1278/monitor/*` module blobs remain unchanged.

## Safety boundary

Stage C performed no physical hardware activity:

- UART: **NO**
- RF: **NO**
- flash: **NO**
- GPIO/reset: **NO**
- option bytes: **NO**

Product TX policy did not change. Automatic firmware flash remains forbidden. Beaconing remains unavailable pending 0F.

Retention is deliberately **not automated**. The previously qualified retention controller remains an explicit maintenance facility only; Stage C does not schedule or call retention apply.

Diagnostics subscriber-drop warnings are operator-visible observations and do not automatically stop packet service. A configured SQLite logger that actually dies or records a write failure is treated as a product health failure because the operator explicitly requested persistent logging.

## Not proven by Stage C

This host qualification does **not** claim:

- installed Raspberry Pi/systemd operation
- real UART or HAT operation through the product daemon
- physical RF RX/TX from the Stage-C daemon graph
- installer/runtime integration
- firmware backup/flash/readback integration
- retention automation
- classic TNC console composition
- fresh Raspberry Pi OS qualification

Those remain later fresh-install integration gates.

## Next stage

Compose the already-qualified classic TNC command transports/personality around this Stage-C product runtime without changing the frozen packet engine or 0D monitor implementations.
