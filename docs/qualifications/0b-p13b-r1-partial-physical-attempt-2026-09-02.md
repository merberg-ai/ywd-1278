# 0B-P13b-R1 Three-Packet Verification — Partial Physical Attempt — 2026-09-02

Status: **PARTIAL PHYSICAL ATTEMPT — HARNESS COUNTER BUG IDENTIFIED — NOT EXTERNALLY QUALIFIED**

## Entering state

- staged head: `84131ee1b6d1ca84001ef6839607ad8ee74d07aa`
- staged checkpoint: `checkpoint/0b-p13b-r1-three-tx-staged-green`
- target: `mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`
- firmware: exact P10/P12 packet image already installed
- frequency: `145.050 MHz`
- RF power byte: `1/255`
- requested sequence: three fixed packets with 5.0 s pauses

## User-observed result

The R1 tool completed staging/vector validation, opened the single owner, passed exact firmware identity and idle/setup gates, submitted burst 1 through the bounded broker, waited for the burst to finish, and then raised:

```text
RuntimeError: expected one RF keyup for P13b-R1 burst 1; observed delta=0
```

Because the exception occurs before the first programmed 5.0 s pause, **bursts 2 and 3 were not submitted** by this attempt.

The attempt is not accepted as external RF qualification because no independent decoder result was captured.

## Root cause of the false-negative

Inspection of the frozen firmware source used to build the installed packet image shows that `CAX25AFSKTX::writeSelectors()` resets both diagnostics at the start of every accepted burst:

```cpp
m_keyups = 0U;
m_samplesQueued = 0U;
m_active = true;
```

The same class then increments `m_keyups` when RF actually enters TX and accumulates `m_samplesQueued` while generating the burst. These values therefore describe the **current/most recently accepted burst**, not a lifetime cumulative total across multiple accepted bursts.

R1 incorrectly computed a modular delta between the diagnostic values retained from the previous physical P13b one-shot and the post-burst values. The immediately preceding one-shot had ended at:

```text
RF_KEYUPS=0->1
RF_TX_GENERATED_SAMPLES=0->12048
```

With the firmware reset-on-accept semantics, a successful new R1 burst ends again at `keyups=1`, so comparing retained pre-burst `1` to post-burst `1` produces the observed but misleading delta `0`.

Therefore R1's per-burst delta assertion is invalid. The correct per-burst acceptance rule is:

- after each accepted/completed burst, `keyups == 1`;
- after each accepted/completed burst, `generated_samples == selector_count * 16`;
- before a subsequent burst, the previous completed diagnostic values must remain unchanged during the inter-packet pause;
- do not compute a lifetime total from these reset-on-accept counters.

## RF power finding

The R1 retry retained the receive-only setup helper's minimum nonzero power byte `1/255`.

The frozen YWD-MMDVM AX25-5B qualification that previously achieved an independent ordinary packet decode at 145.050 MHz used **`200/255` RF power**. P13b-R2 therefore reuses that already independently qualified level rather than inventing a new RF power setting.

## Safety / accounting conclusion

- exact packet firmware identity gate passed before the attempted burst;
- one broker submission was reached;
- the tool failed before submitting bursts 2 and 3;
- no automatic retry path existed;
- KISS/product TX remained disconnected;
- no firmware flash, GPIO/reset, or option-byte operation occurred;
- cleanup ran through the tool's `finally` path;
- this R1 result does **not** close P13b because external decode is still missing.

## Next step

P13b-R2 must:

1. preserve R1 unchanged as historical evidence;
2. use three newly labeled fixed `R2 VERIFY 1/3..3/3` frames;
3. retain 5.0 s fixed inter-packet gaps;
4. use the exact previously independently decoded 145.050 MHz / `200/255` RF profile;
5. treat TX diagnostics as reset-on-accepted-burst values;
6. require `keyups == 1` and exact generated sample count after each burst;
7. stop immediately on any internal mismatch with no automatic retransmission;
8. still require at least one exact independent external decode before P13b can be qualified.
