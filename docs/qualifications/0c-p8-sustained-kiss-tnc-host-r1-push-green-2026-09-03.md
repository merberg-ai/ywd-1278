# 0C-P8 sustained KISS TNC host R1 — dedicated CI green

Date: 2026-09-03

The first exact-head dedicated R1 push gate passed on implementation/staging head:

`717e4530d42ec6264f4a794c79bd8f5911f15f55`

GitHub Actions:

- workflow: `p8-r1-ci`
- run number: 1
- run ID: `33808165383`
- conclusion: **success**

The run passed the new continuously-producing RX FIFO regression, the existing
P8 concurrent bounded admission test, the complete sustained localhost KISS
integration, the updated architecture/safety contract, P7 ingress/evidence,
P6 control-plane, P4e lifecycle, and P5 TXDELAY regressions.

Physical TX remains unauthorized pending the full PR suite, final R1 evidence
commit, exact-head rerun, merge to `dev`, and a new frozen R1 checkpoint.
