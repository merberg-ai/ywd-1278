# 0H-P10 LinBPQ delivery physical qualification

0H-P10 is physically qualified at 145.050 MHz above frozen host checkpoint `checkpoint/0h-p9-linbpq-dialogue-host-qualified` (`618585fd2588235296a281022cf39feb5f2ba8e9`). The successful candidate is `da7c7975b4651e06a7a9d7aeff37ab19eafd8525`, executed with the guarded R3 harness.

## Qualified physical target

- RF frequency: 145.050 MHz
- RF power: 200/255
- local AX.25 source: `KJ6YWD-10`
- LinBPQ listener: `KJ6YWD-5`
- BBS identity: `KJ6YWD-1`
- requested personal-message destination: `KJ6YWD-15`
- LinBPQ stored recipient: `KJ6YWD`
- subject: `P10 TEST`
- body: `YWD-1278 0H-P10 LINBPQ DELIVERY 1/1`
- LinBPQ message number: `464`
- BID: `464_KJ6YWD`
- stored size: 37 bytes

LinBPQ accepted and stored the message, emitted its normal no-forwarding-route warning, returned the exact BBS prompt `de KJ6YWD>`, and remained connected long enough for the local link to complete an orderly DISC/UA release.

## Executed dialogue

The frozen P9 state machine drove exactly:

1. `SP KJ6YWD-15<CR>`
2. `P10 TEST<CR>`
3. `YWD-1278 0H-P10 LINBPQ DELIVERY 1/1`
4. `<CR>`
5. `/EX<CR>`

The live remote transcript then returned:

```text
Message: 464 Bid:  464_KJ6YWD Size: 37
Message is not for a local user, and no forwarding info is available - msg may not be delivered
de KJ6YWD>
```

The warning is informational for this qualification. P10 proves successful submission to the remote BBS and returned-prompt completion; it does not require LinBPQ to have a subsequent forwarding route for the stored message.

## Physical harness revisions

The first physical attempt submitted and stored message 461, but the original harness used MAXFRAME 4 and a 128-byte connected PACLEN; it never delivered the post-`/EX` prompt back into P9. R2 changed only the live RF adapter to stop-and-wait MAXFRAME 1 and stored message 463, but the same post-submit receive failure remained.

R3 retained stop-and-wait and widened only the connected receive PACLEN to 256 bytes. P10's outbound information function remained independently capped at 128 bytes. This allowed the coalesced LinBPQ post-submit information frame, which is larger than 128 bytes, to be accepted without broadening outbound payloads.

R3 additionally logs explicit receive rejection diagnostics and remains bounded at 256 bytes.

## Pass criteria satisfied

- SABM/UA to `KJ6YWD-5`: PASS
- BBS entry command submitted: PASS
- BPQ SID observed before the exact BBS prompt: PASS
- live title prompt: PASS
- live body prompt: PASS
- exact P9 action sequence `SP,TITLE,BODY,BODY_END,END`: PASS
- returned BBS prompt after `/EX`: PASS
- orderly DISC/UA: PASS
- link actions submitted: 13
- exactly one message submitted: PASS
- normal service restored: PASS
- persistent TX final state disabled: PASS
- persistent config unchanged: PASS
- no flash write: PASS
- no option-byte write: PASS

Persistent config SHA256 before/after was `2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76`.

## Frozen evidence

Machine-readable target evidence is stored in `firmware/qualification/0h-p10-linbpq-delivery-target-pi.json` and pinned by `tests/linbpq_delivery_0h_p10_physical_evidence_contract_test.py`.

The executed R3 harness Git blob is `c4399d6be22d00b4bee5d9731cea34d38ca1b7a0`. Frozen P9 remains unchanged at blob `6c3776b7ffe92cb6216c682fc7c12081c57d12aa`.
