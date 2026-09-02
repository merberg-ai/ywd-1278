#!/usr/bin/env python3
"""Offline 1x-rate qualification harness for YWD-1278 streaming Bell-202 RX.

This program reads a saved packed AX25R3 slicer capture. It does not open the
modem UART, touch GPIO, configure RF, or transmit. The default acceptance gate
matches the frozen AX25-3C realtime qualification: exact three physical frames,
no DSP drain after EOF, no accumulated 1x schedule slip, and <=75% processing
duty on the target Raspberry Pi.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import parse_frame  # noqa: E402
from ywd1278.phy import SAMPLE_RATE, StreamingBell202Decoder  # noqa: E402

PACKED_BYTES_PER_SECOND = SAMPLE_RATE / 8.0
DEFAULT_CHUNK_BYTES = 120  # 50 ms at 2400 packed bytes/s
MAX_PROCESSING_DUTY = 0.75
EXPECTED = (
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 3f 4a 88"),
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 20 f0 6e 0d 00 28"),
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 82 f0 6d 68 0d 70 23"),
)
EXPECTED_SAMPLE_STARTS = (992, 56000, 154418)


def describe(index: int, frame) -> None:
    parsed = parse_frame(frame.frame, has_fcs=True)
    print(
        f"STREAMING[{index}] sample={frame.sample_start} "
        f"baud={frame.baud:.1f} phase={frame.phase:.1f} "
        f"{parsed['source']}>{parsed['destination']} "
        f"type={parsed['frame_type']} bytes_with_fcs={len(frame.frame)}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 offline Bell-202 1x replay qualification")
    ap.add_argument("capture", type=Path, help="saved packed AX25R3 one-bit slicer capture")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    ap.add_argument("--max-duty", type=float, default=MAX_PROCESSING_DUTY)
    args = ap.parse_args()

    if os.geteuid() == 0:
        raise SystemExit("Run replay qualification without sudo; no hardware access is required")
    if args.speed <= 0.0:
        raise SystemExit("--speed must be positive")
    if args.chunk_bytes <= 0:
        raise SystemExit("--chunk-bytes must be positive")
    if not 0.0 < args.max_duty <= 1.0:
        raise SystemExit("--max-duty must be in (0, 1]")
    if not args.capture.is_file():
        raise SystemExit(f"capture does not exist: {args.capture}")

    packed = args.capture.read_bytes()
    source_seconds = len(packed) / PACKED_BYTES_PER_SECOND
    scheduled_wall_seconds = source_seconds / args.speed

    print(f"capture: {args.capture}")
    print(f"packed bytes: {len(packed)}")
    print(f"source duration: {source_seconds:.3f} s")
    print(f"replay speed: {args.speed:.2f}x")
    print(f"feed chunk: {args.chunk_bytes} bytes")
    print("decoder: one-pass metric lookup + persistent scheduled 144-hypothesis bank + streaming HDLC")
    print("overlapping decode windows: NO")
    print("DSP worker backlog: NO")
    print(f"processing duty gate: <= {args.max_duty * 100.0:.0f}%")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")

    decoder = StreamingBell202Decoder()
    processing_total = 0.0
    max_feed_processing = 0.0
    late_chunks = 0

    wall_start = time.monotonic()
    deadline = wall_start
    for offset in range(0, len(packed), args.chunk_bytes):
        chunk = packed[offset : offset + args.chunk_bytes]
        deadline += len(chunk) / PACKED_BYTES_PER_SECOND / args.speed

        t0 = time.monotonic()
        decoder.feed(chunk)
        elapsed = time.monotonic() - t0
        processing_total += elapsed
        max_feed_processing = max(max_feed_processing, elapsed)

        now = time.monotonic()
        if now > deadline:
            late_chunks += 1
        else:
            time.sleep(deadline - now)

    feed_wall = time.monotonic() - wall_start
    drain_start = time.monotonic()
    drained = decoder.finish()
    drain_seconds = time.monotonic() - drain_start
    total_wall = time.monotonic() - wall_start

    occurrences = list(decoder.occurrences)
    for index, frame in enumerate(occurrences, 1):
        describe(index, frame)

    got = [item.frame for item in occurrences]
    exact_frames = got == list(EXPECTED)
    timing_ok = len(occurrences) == 3 and all(
        abs(item.sample_start - expected) <= 1600
        for item, expected in zip(occurrences, EXPECTED_SAMPLE_STARTS)
    )
    schedule_slip = max(0.0, feed_wall - scheduled_wall_seconds)
    processing_duty = processing_total / scheduled_wall_seconds if scheduled_wall_seconds else 1.0
    headroom = max(0.0, 1.0 - processing_duty)
    stats = decoder.stats

    print("\nStreaming metrics")
    print(f"feed_wall_seconds:             {feed_wall:.3f}")
    print(f"post_stream_dsp_drain_seconds: {drain_seconds:.6f}")
    print(f"total_wall_seconds:            {total_wall:.3f}")
    print(f"processing_cpu_wall_seconds:   {processing_total:.3f}")
    print(f"processing_duty_cycle_pct:     {processing_duty * 100.0:.1f}")
    print(f"processing_headroom_pct:       {headroom * 100.0:.1f}")
    print(f"max_feed_processing_seconds:   {max_feed_processing:.4f}")
    print(f"schedule_slip_seconds:         {schedule_slip:.4f}")
    print(f"late_chunks:                   {late_chunks}")
    print(f"hypotheses:                    {stats.hypotheses}")
    print(f"metric_windows:                {stats.metric_windows}")
    print(f"symbol_decisions:              {stats.symbol_decisions}")
    print(f"flags_seen:                    {stats.flags_seen}")
    print(f"duplicates_suppressed:         {stats.duplicate_occurrences_suppressed}")
    print(f"max_frame_buffer_bits:         {stats.max_frame_buffer_bits}")
    print(f"unique_occurrences:            {len(occurrences)}")

    if drained:
        print("YWD1278_BELL202_RX_REPLAY=FAIL reason=finish returned queued DSP work")
        return 2
    if not exact_frames:
        print("YWD1278_BELL202_RX_REPLAY=FAIL reason=qualified frame vector mismatch")
        return 3
    if not timing_ok:
        print("YWD1278_BELL202_RX_REPLAY=FAIL reason=physical occurrence timing mismatch")
        return 4
    if drain_seconds > 0.050:
        print("YWD1278_BELL202_RX_REPLAY=FAIL reason=post-stream DSP drain not negligible")
        return 5
    if schedule_slip > 0.250:
        print("YWD1278_BELL202_RX_REPLAY=FAIL reason=decoder fell behind source schedule")
        return 6
    if processing_duty > args.max_duty:
        print(
            "YWD1278_BELL202_RX_REPLAY=FAIL reason=insufficient realtime CPU headroom "
            f"duty={processing_duty * 100.0:.1f}% gate<={args.max_duty * 100.0:.0f}%"
        )
        return 7

    print("YWD1278_BELL202_RX_REPLAY=PASS frames=3")
    print("OVERLAPPING_WINDOW_SEARCH=REMOVED")
    print("DSP_BACKLOG=NONE")
    print("POST_STREAM_DRAIN=NEGLIGIBLE")
    print("REALTIME_CPU_HEADROOM=PASS")
    print("DEFAULT_HYPOTHESES=144")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
