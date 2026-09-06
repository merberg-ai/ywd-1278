# 0H-P11 forwarding plumbing host qualification

0H-P11 is host-qualified above frozen checkpoint `checkpoint/0h-p10-linbpq-delivery-physically-qualified` (`77af814a596f717bea3dca967b1ce9b5a83c49fe`).

## Qualified boundary

- bounded caller-driven coordinator over frozen 0H-P8 forwarding preparations;
- maximum batch remains 8;
- injected delivery driver only;
- `ACCEPTED` produces an inert commit intent and does not mutate storage;
- `REJECTED` and `UNCERTAIN` stop the batch fail-closed;
- driver exceptions become `UNCERTAIN` and are never automatically retried;
- disabled coordinator performs zero planning and zero delivery calls;
- `[forwarding]` configuration defaults to `enabled=false`, `interval_seconds=900`, `max_batch=8`;
- missing `[forwarding]` retains those safe disabled defaults for historical configs;
- `forwarding.enabled=true` is rejected until deferred physical forwarding qualification;
- normal daemon parses the forwarding config and reports `FORWARDING=DISABLED` / `FORWARDING_PHYSICAL_QUALIFICATION=DEFERRED`, but does not instantiate the coordinator.

## Frozen lineage

P11 preserves the already-qualified forwarding and live-delivery boundaries byte-exact:

- 0H-P8 forwarding integration blob `263b5583d473a5673e6dfa60978804055197f676`;
- 0H-P9 LinBPQ dialogue blob `6c3776b7ffe92cb6216c682fc7c12081c57d12aa`;
- 0H-P10 R3 physical harness blob `c4399d6be22d00b4bee5d9731cea34d38ca1b7a0`;
- 0H-P10 physical evidence blob `617d891bce3b106a1744a2418b6788e92e16659c`.

The P11 qualified core is pinned by `tests/forwarding_plumbing_0h_p11_qualification_contract_test.py`:

- forwarding config blob `f30617e6611997faf8ef2cc016b4d787012b097e`;
- forwarding coordinator blob `ce4ee0b1b132ac6881a48f8e20b0c2c1322dac52`;
- host behavior test blob `0afaec3da29fd35273f40d455de5f3b6d9a43cf0`.

Candidate implementation head `82e379e8edb7b9cd0d8d3a73a3a4ac9d1e06d89f` passed GitHub Actions run `34007415432` after the only initial CI failure was corrected (test temporary-directory cleanup ordering; no product behavior change).

## Physical forwarding deferred

The available LinBPQ installation is not configured as a reliable forwarding peer. 0H-P10 proves one real classic `SP` delivery transaction, but that is not sufficient to claim automatic BBS-to-BBS forwarding qualification.

0H-P12 is therefore explicitly deferred until a forwarding-capable peer or dedicated test system is available. Before `forwarding.enabled=true` can be permitted, a future physical qualification must prove configured peer routing, stored-message selection, remote forwarding acceptance, exact-once local delivery-state commit, restart/backoff behavior, and duplicate suppression.

## Explicitly absent

No forwarding scheduler, background thread, mailbox enumeration, mailbox schema change, mailbox mutation, connected-link owner, modem/UART access, RF transmission, flash, GPIO/reset, or option-byte write is added by P11.
