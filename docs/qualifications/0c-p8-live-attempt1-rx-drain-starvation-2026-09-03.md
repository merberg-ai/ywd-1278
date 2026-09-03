# 0C-P8 live sustained KISS — physical attempt 1 failure

Date: 2026-09-03

Status: **failed safely before any TX dispatch / preserved historical evidence**

Physical staging head used for the attempt:

`6b54fa8b3797ea5bc6faeadd911149b6d9dc8ae7`

Historical host checkpoint beneath that stage:

`checkpoint/0c-p8-sustained-kiss-tnc-host-qualified`

`a835d2500dbdb4a8eaf1ae3cae4ea662203a852a`

## Observed result

The guarded P8 physical harness opened cycle 1 on 145.050 MHz. Multiple real
AX.25 packets were transmitted toward the HAT, but cycle 1 never reached the
guarded dispatch condition. The harness ended with:

`RuntimeError: timed out waiting for cycle 1 guarded sustained TX`

No P8 qualification TX had been accepted before the failure. The attempt is
therefore safe to supersede and repeat only after the host regression is fixed
and requalified.

## Root cause

The P8 host scheduler changed the previously physically-qualified P4e/P7 RX
service discipline in order to guarantee that already-captured packed RX data
could not be overtaken by a later half-duplex TX. Its `_drain_rx_fifo()` loop
continued issuing `YWD_RX/READ` until one read returned zero bytes.

That assumption is valid for the P8 fake modem's finite bytearray but false for
the real AX25R4 receive engine. While RX is active, AX25R4 continuously samples
the demodulated bit stream at 19.2 ksps and packs those samples into its 512-byte
FIFO even during RF silence. New bytes can therefore arrive between UART read
transactions. A scheduler that insists on observing an exact zero-length read
can chase the live sampler indefinitely.

The consequence in attempt 1 was scheduler starvation: RX_READ transactions
could continue while the worker never yielded to the subsequent RSSI/P2/P1
channel-access step. The queued KISS frame therefore could not observe the
required BUSY/clear/persistence sequence or dispatch.

## Why host CI missed it

`tests/p8_fake_modem.py` modeled RX with a finite bytearray. Once injected test
capture bytes were consumed, `RX_READ` returned an empty payload. That model
proved finite backlog ordering but did not represent the continuously-producing
physical sampler.

## R1 correction

The R1 host repair restores the bounded live-drain discipline already proven by
the physical P4e/P7 tests:

- maximum RX read: 200 packed bytes;
- hardware RX FIFO: 512 packed bytes;
- maximum reads per scheduler drain pass: 4;
- maximum service capacity per pass: 800 bytes;
- a partial read ends the pass immediately;
- an exact zero-length read is not required;
- after the bounded pass, RSSI/CSMA receives a scheduling opportunity before RX
  backlog is serviced again.

Four maximum-size reads can consume more than one complete hardware FIFO
snapshot while remaining bounded against continuous sample production.

A new regression fake explicitly never returns an empty RX_READ. The scheduler
must still return after exactly four reads. A second regression proves that a
partial read stops the drain without issuing another read merely to seek zero.

## Safety

- accepted P8 TX before failure: **0**
- RF qualification packets transmitted by P8 harness: **0**
- automatic retry: **no**
- flash: **not touched**
- GPIO/reset: **not touched**
- option bytes: **not touched**
- product/daemon TX: **disabled**

The failed physical staging branch and its draft PR remain historical evidence
and must not be promoted. Physical P8 resumes only from a new R1 host checkpoint
and a separately staged R2 physical branch after exact-head CI is green.
