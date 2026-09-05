# YWD-1278 Stage I — physical single-shot product TX qualified

Date: 2026-09-04 (America/Los_Angeles)

## Result

**PHYSICALLY QUALIFIED.**

Stage I proved the installed product TX path on 145.050 MHz while preserving the product's persistent no-TX default.

## Frozen lineage

- Stage H final: `checkpoint/product-fresh-os-stage-h-qualified` @ `e7e203ba6ef76a0465ff6c25ef9671a46a4ab582`
- Stage I host-qualified harness: `checkpoint/product-fresh-os-stage-i-single-tx-host-qualified` @ `0b0e288e619368f2b3d8928e241efd806b2df442`
- Stage I pre-RF target-Pi gate: `checkpoint/product-fresh-os-stage-i-pre-tx-qualified` @ `a54f51c93415d2652e0f7204bf7209fab41a25d7`
- Installed product commit under test: `2f5299e65add072fea6ee55a54dc421faf00c276`

## Qualified RF vector

- Frequency: 145.050 MHz
- TX power: 200/255
- Source: `KJ6YWD-10`
- Destination: `YWD127`
- Digipeater path: none / direct
- Information: `YWD-1278 STAGE-I TX 1/1`
- KISS DATA body: 39 bytes
- Body SHA-256: `7ce21d988402ca554cbb7f8c4626cddda9f8f2b970bb53a79ccf2264be67e7e2`
- Firmware SHA-256 reverified immediately before the physical run: `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`

## Physical observations

The guarded Stage-I harness revalidated service eligibility and exact AX25R4 HAT identity, launched the installed product daemon against a root-only temporary `/run` TX configuration, and injected exactly one KISS DATA message.

Observed product accounting:

- KISS DATA injected: 1
- internal TX dispatches: 1
- queue accepted: 1
- queue dispatched: 1
- second dispatch during hold: none
- automatic retry: none

The operator then confirmed that an independent 145.050 MHz packet receiver decoded the exact expected frame once. The independent receiver's raw decoder transcript was not archived, so the evidence claim is intentionally phrased as **operator-confirmed exact independent decode**, not machine-captured decoder-log evidence.

After TX, the product RX path resumed and delivered a later non-qualification packet:

- frame bytes: 73
- source: `KJ6YWD`
- source differs from Stage-I TX source `KJ6YWD-10`: yes

Final runtime health/accounting:

- final TX dispatches: 1
- TX queue depth: 0
- subscriber drops: 0
- TX access timeouts: 0
- TX downstream failures: 0

Cleanup/safety:

- persistent TX enabled: no
- persistent config mutated: no
- normal no-TX service restored: yes
- firmware flash written: no
- option bytes written: no

## Qualified claim

Stage I physically qualifies the product path:

`localhost KISS DATA -> bounded admission -> CSMA/channel access -> installed product daemon -> AX25R4 HAT -> Bell-202 RF -> operator-confirmed exact independent decode`

and proves that receive operation resumes afterward with clean queue/subscriber accounting.

This acceptance test consumes only the explicitly authorized one-shot Stage-I TX authority. It does **not** enable persistent TX by default and does not authorize later beaconing, UNPROTO/converse, or connected-mode behavior. Those remain separately staged product features.

## Evidence

- `firmware/qualification/0b-product-fresh-os-stage-i-dry-run-target-pi.json`
- `firmware/qualification/0b-product-fresh-os-stage-i-tx-target-pi.json`
- `firmware/qualification/0b-product-fresh-os-stage-i-tx-acceptance.json`
- `tests/fresh_os_stage_i_physical_tx_evidence_contract_test.py`
- final evidence-bearing CI run `33935986407` — success
