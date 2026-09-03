# 0C-P2 packet/RSSI correlation R1 staging superseded — 2026-09-02

## Status

**SUPERSEDED BEFORE PHYSICAL EXECUTION.**

The host-only staging checkpoint
`checkpoint/0c-p2-rssi-packet-correlation-staged-green` at
`409f1e424c614d3c248c8872a6269d72589c9b96` passed its then-current CI, but its
live packet/RSSI characterization logic was not executed on hardware.

Before handing that command to the operator, review found that its polarity
assertion was partially circular: packet-correlated RSSI was used to choose a
guard gap and packet RSSI was then checked against the midpoint derived from
that same packet-referenced gap. That can describe separation but cannot serve
as an independent proof that lower raw ADF7021 magnitude means stronger RF.

## Corrected staging

The corrected gate requires:

- two distinct, decoder-deduplicated, FCS-valid AX.25 frame events;
- exact frame/RSSI sample-position correlation;
- an independent outside-frame RSSI population, excluding +/-0.5 s around each
  decoded frame;
- every run to preserve zero RF keyup / zero generated TX samples;
- the worst decoded-frame RSSI median to be at least 12 raw counts lower than
  the outside-frame median before polarity is accepted;
- only after that independent polarity proof, a descriptive packet-referenced
  guard gap with at least 12 raw counts of separation;
- no carrier threshold, hysteresis, busy/clear decision, CSMA integration,
  KISS TX, product TX, firmware write, GPIO access, or option-byte access.

Fewer than two valid frames is an **incomplete, safe-to-repeat** observation,
not a qualification failure and not permission to weaken the evidence rule.

The R1 staging checkpoint remains frozen for audit history and must never be
moved or used for physical qualification.
