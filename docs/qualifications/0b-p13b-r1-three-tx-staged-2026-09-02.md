# 0B-P13b-R1 Three-Packet External-Decode Assist — 2026-09-02

Status: **STAGED / CI-GATED — PHYSICAL R1 SEQUENCE NOT YET RUN**

The first 0B-P13b physical one-shot produced exact internal RF evidence but could not be confirmed by an independent receiver/decoder. That original test is preserved unchanged in `p13b-single-tx.json`, `tools/qualify_single_tx.py`, and the frozen branch `checkpoint/0b-p13b-single-tx-staged-green`.

The first-run evidence is separately recorded in `docs/qualifications/0b-p13b-internal-single-tx-evidence-2026-09-02.md` as **internal RF TX passed / external decode unverified**.

0B-P13b-R1 is a bounded external-decode-assist retry. It does not create a general transmit interface.

## Fixed physical target

- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- UART: `/dev/ttyAMA0`
- frequency: `145050000 Hz`
- running firmware: exact qualified P10/P11/P12 AX25R3 packet identity required
- RF power field: frozen simplex SET_FREQ minimum nonzero byte `1/255`
- ordinary KISS TX: disconnected
- persistent product TX: disabled
- flash: prohibited
- GPIO/reset: prohibited
- option-byte write: prohibited

## Fixed sequence

The R1 harness may submit exactly three frames. They are separated by exactly `5.0 s` between completed bursts.

### Burst 1/3

Expected external decode:

`KJ6YWD-10>YWD13B:YWD-1278 P13B VERIFY 1/3`

- AX.25 bytes: `42`
- AX.25 hex: `b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920312f3373a3`
- AX.25 SHA256: `f2e11d43587cab7b30d3bfafeb178b42ba3635a89b25902bc4d126c3e05b6ab2`
- selectors: `721`
- packed selector bytes: `91`
- packed selector SHA256: `9abce15293666e5718011191ebaa4fa9e7e4cdf0ff24b14a24b527a0e1184e04`
- expected generated samples: `11536`

### Burst 2/3

Expected external decode:

`KJ6YWD-10>YWD13B:YWD-1278 P13B VERIFY 2/3`

- AX.25 bytes: `42`
- AX.25 hex: `b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920322f33174c`
- AX.25 SHA256: `777cae2a3d70d5e458bd8fd8fde9165a4e0ac158e1ecf48d2ca8d3ca90fcccc4`
- selectors: `721`
- packed selector bytes: `91`
- packed selector SHA256: `b5e2bc3485c433fd3722860b14759269a6ce150d6f864c51018f2428938c102b`
- expected generated samples: `11536`

### Burst 3/3

Expected external decode:

`KJ6YWD-10>YWD13B:YWD-1278 P13B VERIFY 3/3`

- AX.25 bytes: `42`
- AX.25 hex: `b2ae88626684e096946cb2ae887503f05957442d3132373820503133422056455249465920332f33cb16`
- AX.25 SHA256: `e79795fceb05569fcb825ac9e98cf3b5decd08a3185ca31c5f9851b39920b321`
- selectors: `721`
- packed selector bytes: `91`
- packed selector SHA256: `080d92f1e6db8d0a1fd24ba61ed6cd06601d6e548d124f262b7ebb029f5b687a`
- expected generated samples: `11536`

## Aggregate internal proof required

A successful R1 physical run must report:

- transmit submissions: exactly `3`
- RF keyup delta: exactly `3`
- generated-sample delta: exactly `34608`
- every individual burst: exactly `+1` keyup and `+11536` samples
- remaining selectors: zero after each burst and at final shutdown
- TX inactive after each burst and at final shutdown
- UART released after the sequence

Counter checks are delta-based, so the earlier one-shot's existing physical counters do not need to be reset.

## External proof required

At least one of the three exact known frames must be independently decoded by a separate receiver/TNC/decoder. The unique `1/3`, `2/3`, and `3/3` information strings identify which physical burst was received.

One exact independent decode is sufficient to prove the over-air Bell-202/AX.25 content because all three host vectors are independently locked in CI and each physical burst is separately tied to the expected internal keyup/sample delta. Multiple independent decodes are preferred evidence and should all be recorded if observed.

## Operator controls

The R1 physical tool accepts only:

- `--transmit`
- `--confirm P13B-R1-145050-VERIFY-3`

It does not accept user-selectable target, UART, frequency, source, destination, payload, transmit count, pause, serializer parameters, or staging file.

The default invocation is dry-run and returns before the TX owner or UART is constructed/opened.

## Failure semantics

There is no automatic TX retry.

If any broker submission returns an error, the tool stops; it does not resubmit that frame and does not proceed as though the failed burst were safe to repeat. This matters because RF may already have occurred before a host-side error is observed.

## Qualification boundary

P13b remains incomplete until the R1 sequence is physically run and external decode evidence is supplied. The hardware target therefore remains at the frozen `0b-p12b-live-rf-kiss-qualified` status.
