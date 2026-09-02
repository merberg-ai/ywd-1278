# 0B-P6 Streaming Bell-202 RX Port Qualification — 2026-09-02

Status: **QUALIFIED — host-side realtime physical-capture replay**

## Qualification boundary

- repository: `merberg-ai/ywd-1278`
- branch under qualification: `dev`
- qualifying code boundary: `7c9547747bc53c3a2587403af63f0211482fcd58`
- CI workflow run: `33650787834` — **SUCCESS**
- source lineage: `merberg-ai/ywd-mmdvm` frozen checkpoint `d25180ad663d781b761c525d1e699e7b052d6214`
- qualified source implementation: `tools/packetd/streaming_rx.py`
- source blob: `5f31d97a264557ca985e028b50dcbdeda05672ab`

This qualification ports and requalifies the already-proven incremental Bell-202 receive DSP architecture. It does **not** open the modem UART, configure RF, key the transmitter, or qualify the final always-on service.

## Product implementation

YWD-1278 implementation:

- `src/ywd1278/phy/bell202_rx.py`
- `tests/bell202_rx_test.py`
- `tools/qualify_bell202_rx_replay.py`

Steady-state receive architecture:

```text
19.2 ksps packed one-bit slicer samples
  -> exact 12-bit Bell-202 metric lookup (4096 entries)
  -> persistent 1196..1204 baud x 16-phase acquisition bank
  -> 144 persistent timing hypotheses
  -> heap-scheduled symbol decisions
  -> NRZI
  -> streaming HDLC / de-stuffing
  -> AX.25 FCS + structural validation
  -> physical-occurrence dedupe
```

The port deliberately preserves the qualified one-pass architecture. Exhaustive overlapping-window rescans are not used in the steady-state decoder.

## CI equivalence gate

GitHub Actions run `33650787834` completed successfully at the qualifying code boundary.

The deterministic regression suite proves:

- exact Bell-202 metric-table equivalence against the qualified correlation reference;
- all three frozen physical AX25R3 frame vectors decode in order;
- arbitrary feed chunk boundaries do not change decode results;
- identical packets at separate physical occurrences remain separate events;
- `finish()` has no queued DSP drain;
- the default acquisition bank remains exactly 144 hypotheses;
- all earlier installer, firmware, AX.25 codec, and Bell-202 TX safety regressions remain green.

## Raspberry Pi realtime replay

The saved physical AX25R3 capture was replayed on `pi5-norm` at exactly the physical receive rate.

Capture:

```text
/home/ywd/mmdvm-lab/ywd-mmdvm/logs/ax25-rx3-raw-20260901-174007.bin
packed bytes: 24009
source duration: 10.004 s
physical sample rate: 19.2 ksps
packed receive rate: 2400 bytes/s
feed chunk: 120 bytes / 50 ms source time
replay speed: 1.00x
```

The capture is a previously-recorded real RF receive capture from the qualified AX25R3 hardware path. The P6 replay itself is offline and performs no current RF operation.

### Exact recovered physical occurrences

```text
STREAMING[1] sample=998 baud=1200.0 phase=7.0 KJ6YWD-1>RDG type=SABM bytes_with_fcs=17
STREAMING[2] sample=56008 baud=1198.0 phase=12.0 KJ6YWD-1>RDG type=I bytes_with_fcs=20
STREAMING[3] sample=154432 baud=1200.0 phase=1.0 KJ6YWD-1>RDG type=I bytes_with_fcs=21
```

The harness requires the exact frozen frame bytes in the exact expected order before it can emit PASS.

Reference occurrence starts from the original qualification were `992`, `56000`, and `154418`; the productized decoder recovered them at `998`, `56008`, and `154432`, preserving the previously-qualified timing behavior.

### Realtime metrics

```text
feed_wall_seconds:             10.004
post_stream_dsp_drain_seconds: 0.000002
total_wall_seconds:            10.004
processing_cpu_wall_seconds:   5.253
processing_duty_cycle_pct:     52.5
processing_headroom_pct:       47.5
max_feed_processing_seconds:   0.0335
schedule_slip_seconds:         0.0001
late_chunks:                   0
hypotheses:                    144
metric_windows:                192061
symbol_decisions:              1728513
flags_seen:                    21568
duplicates_suppressed:         145
max_frame_buffer_bits:         2216
unique_occurrences:            3
```

Acceptance gate: processing duty must be `<= 75%`. Observed duty was **52.5%**, leaving **47.5% measured processing headroom**. No feed chunk was late, accumulated schedule slip was negligible, and post-stream DSP drain was effectively zero.

## Final acceptance markers

```text
YWD1278_BELL202_RX_REPLAY=PASS frames=3
OVERLAPPING_WINDOW_SEARCH=REMOVED
DSP_BACKLOG=NONE
POST_STREAM_DRAIN=NEGLIGIBLE
REALTIME_CPU_HEADROOM=PASS
DEFAULT_HYPOTHESES=144
MODEM_UART_OPENED=NO
RF_TRANSMITTED=NO
```

## Safety properties retained

- no modem UART opened by the replay harness;
- no RF configuration;
- no RF transmission or key-up;
- no firmware write or flash operation;
- STM32 option bytes were not written;
- no overlapping-window DSP backlog;
- no automatic RF behavior;
- existing firmware/installer safety contracts remained green.

## Qualification conclusion

**0B-P6 is QUALIFIED.**

YWD-1278 now has a productized host-side realtime Bell-202 receive decoder that preserves the frozen YWD-MMDVM physical-frame behavior and meets the realtime CPU budget on the target Raspberry Pi.

This qualifies the **streaming DSP implementation and 1x physical-capture replay throughput only**. It does not yet qualify live UART ownership, live RF receive, TCP KISS publication, RX/TX sequencing, or physical YWD-1278 transmission. Those remain later 0B gates.
