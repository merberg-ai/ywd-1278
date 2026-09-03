# 0C-P8 sustained KISS TNC host R1 — qualified

Date: 2026-09-03

Status: **host-qualified / physical follow-on still gated pending final evidence-head CI**

Base checkpoint:

`checkpoint/0c-p8-sustained-kiss-tnc-host-qualified`

`a835d2500dbdb4a8eaf1ae3cae4ea662203a852a`

## Result

Physical P8 attempt 1 exposed a scheduler assumption that the host-only fake did
not model: the real AX25R4 RX sampler continuously produces packed bytes while
RX is active, so an RX service loop cannot require an exact empty `RX_READ`
before yielding to RSSI/CSMA.

R1 replaces the zero-seeking loop with a hardware-derived bounded backlog pass:

- AX25R4 packed FIFO capacity: 512 bytes
- maximum `RX_READ`: 200 bytes
- maximum reads per scheduler pass: 4
- maximum service capacity: 800 bytes
- partial read ends a pass
- exact zero-length read is not required
- RX remains first in every scheduler iteration
- RSSI/CSMA is guaranteed a scheduling opportunity after at most four full reads

This keeps already-captured receive backlog ahead of queued TX access without
allowing the continuously-producing raw sampler to starve channel access.

## Regression proof

A new host regression source returns a full 200-byte RX payload forever. The R1
scheduler returns after exactly four reads. A second model returns 200 bytes and
then 37 bytes; R1 stops after the partial read and does not seek a third empty
transaction.

The existing sustained localhost KISS integration also still passes four full
TX lifecycle cycles over the fake thread-bound owner, including reconnect,
post-TX Bell-202 decoder reset and post-TX FCS-valid RX delivery.

## Review-head CI

Review head:

`4288cdcaea1ce8f9cd3d15760216f381a8ed7dbb`

Passed:

- `p8-r1-ci` push run #4 / ID `33808277251`
- `p8-r1-ci` PR run #5 / ID `33808307163`
- `p8-ci` PR run #42 / ID `33808307203`
- `framework-ci` PR run #459 / ID `33808307159`
- all other P7/P7-live/P6/P5/P4e/P4e-live/P4d/P4d-R2 PR gates on the same head

No host qualification run opened a UART or transmitted RF.

## Preserved boundaries

R1 does not modify:

- P7 KISS DATA admission
- P6 KISS controls
- P4e half-duplex lifecycle
- P5 TXDELAY routing
- TX broker / Bell-202 TX serializer
- AX25R4 firmware
- daemon product TX policy
- systemd product TX policy

The failed physical attempt and original host checkpoint remain frozen as
historical evidence.

## Next gate

The evidence/documentation head itself must pass exact-head CI. After that, the
R1 manifest may record `final_exact_head_ci=success`, `dev` may be advanced, and
a new checkpoint named
`checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified` may be frozen. Physical
P8 then restages separately as R2; the original physical branch remains
superseded and must not be reused.
