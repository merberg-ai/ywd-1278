# 0H-P11 forwarding plumbing

0H-P11 turns the already-qualified forwarding pieces into a bounded host-only coordinator boundary without activating product forwarding.

## Composition

The coordinator consumes frozen 0H-P8 `ForwardEnvelope` / `PreparedForwardMessage` work from an injected planner and hands only prepared forwarding messages to an injected delivery driver. It is caller-driven and processes one bounded batch at a time.

The delivery driver returns one explicit outcome:

- `ACCEPTED` — the remote side has definitively accepted the message;
- `REJECTED` — the remote side definitively refused it;
- `UNCERTAIN` — the caller cannot prove whether delivery became externally visible.

Only `ACCEPTED` yields an inert `ForwardCommitIntent`. P11 does not apply that intent to mailbox storage. `REJECTED` and `UNCERTAIN` stop the batch immediately, and no automatic retry is attempted.

## Product gate

The product configuration now understands:

```toml
[forwarding]
enabled = false
interval_seconds = 900
max_batch = 8
```

Missing `[forwarding]` retains the same safe disabled defaults so historical configuration fixtures remain valid.

At the P11 boundary `enabled=true` is deliberately rejected during configuration loading. The normal daemon loads the configuration and reports forwarding as disabled/deferred, but it does not instantiate `HostForwardingCoordinator`, enumerate mailbox messages, schedule work, open a connected-mode link, mutate storage, or transmit RF.

## Deferred physical activation

0H-P10 proved one live classic LinBPQ `SP` delivery transaction, but the currently available LinBPQ system is not configured as a reliable BBS forwarding peer. That is sufficient evidence for the dialogue/transport boundary, not for automatic BBS-to-BBS forwarding policy.

0H-P12 is therefore deferred until a forwarding-capable peer or dedicated test system is available. That future stage must qualify route configuration, stored-message selection, real peer forwarding acceptance, exact-once delivery-state commit, restart/backoff behavior, and duplicate suppression before the product gate may allow `forwarding.enabled=true`.

## Explicitly absent

P11 adds no forwarding scheduler, background thread, mailbox enumeration, mailbox schema change, storage mutation, connected-link owner, UART ownership, modem transaction, RF transmission, flash, GPIO/reset, or option-byte operation.
