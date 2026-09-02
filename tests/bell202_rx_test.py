#!/usr/bin/env python3
from __future__ import annotations

import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.phy import (  # noqa: E402
    CORR_WINDOW,
    SAMPLE_RATE,
    StreamingBell202Decoder,
    frame_to_selectors,
)
from ywd1278.phy.bell202_rx import (  # noqa: E402
    DEFAULT_BAUDS,
    DEFAULT_PHASES,
    MARK_HZ,
    SPACE_HZ,
    _METRIC_TABLE,
)

PHYSICAL_SABM = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 3f 4a 88"
)
PHYSICAL_I_N = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 20 f0 6e 0d 00 28"
)
PHYSICAL_I_MH = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 82 f0 6d 68 0d 70 23"
)


def synthesize(
    selectors: list[int],
    *,
    symbol_offset: float = 7.0,
    baud: float = 1200.0,
) -> list[int]:
    period = SAMPLE_RATE / baud
    total = int(math.ceil(symbol_offset + len(selectors) * period)) + 8
    samples: list[int] = []
    phase = 0.37
    for n in range(total):
        relative = n - symbol_offset
        if relative < 0.0:
            samples.append(n & 1)
            continue
        index = int(relative // period)
        selector = selectors[-1] if index >= len(selectors) else selectors[index]
        frequency = SPACE_HZ if selector else MARK_HZ
        samples.append(1 if math.sin(phase) >= 0.0 else 0)
        phase += 2.0 * math.pi * frequency / SAMPLE_RATE
        if phase > 2.0 * math.pi:
            phase -= 2.0 * math.pi
    return samples


def pack(samples: list[int]) -> bytes:
    out = bytearray((len(samples) + 7) // 8)
    for index, value in enumerate(samples):
        if value:
            out[index >> 3] |= 0x80 >> (index & 7)
    return bytes(out)


def reference_metric(pattern: int) -> float:
    values = [
        1.0 if pattern & (1 << (CORR_WINDOW - 1 - index)) else -1.0
        for index in range(CORR_WINDOW)
    ]
    mean = sum(values) / CORR_WINDOW

    def power(frequency: float) -> float:
        omega = 2.0 * math.pi * frequency / SAMPLE_RATE
        c = [math.cos(omega * i) for i in range(CORR_WINDOW)]
        s = [math.sin(omega * i) for i in range(CORR_WINDOW)]
        mc = sum((raw - mean) * ref for raw, ref in zip(values, c))
        ms = sum((raw - mean) * ref for raw, ref in zip(values, s))
        return (mc * mc + ms * ms) / float(CORR_WINDOW * CORR_WINDOW)

    mark = power(MARK_HZ)
    space = power(SPACE_HZ)
    total = mark + space
    return (space - mark) / total if total > 1e-9 else 0.0


class StreamingRXTests(unittest.TestCase):
    def _decode(
        self,
        frames: list[bytes],
        *,
        offset: float = 7.0,
        chunk: int = 37,
    ) -> list[bytes]:
        selectors: list[int] = []
        for frame in frames:
            selectors.extend(frame_to_selectors(frame, pre_flags=20, post_flags=6))
        raw = pack(synthesize(selectors, symbol_offset=offset))
        decoder = StreamingBell202Decoder(
            bauds=(1200.0,),
            phases=tuple(float(v) for v in range(16)),
        )
        for start in range(0, len(raw), chunk):
            decoder.feed(raw[start : start + chunk])
        self.assertEqual(decoder.finish(), [])
        return [item.frame for item in decoder.occurrences]

    def test_metric_table_shape_and_exact_reference(self) -> None:
        self.assertEqual(CORR_WINDOW, 12)
        self.assertEqual(len(_METRIC_TABLE), 4096)
        for pattern in (0x000, 0x001, 0x123, 0x555, 0x789, 0xAAA, 0xFFE, 0xFFF):
            self.assertAlmostEqual(_METRIC_TABLE[pattern], reference_metric(pattern), places=12)

    def test_default_qualified_bank_is_144_hypotheses(self) -> None:
        self.assertEqual(DEFAULT_BAUDS, tuple(float(v) for v in range(1196, 1205)))
        self.assertEqual(DEFAULT_PHASES, tuple(float(v) for v in range(16)))
        decoder = StreamingBell202Decoder()
        self.assertEqual(decoder.stats.hypotheses, 144)

    def test_three_qualified_physical_frame_vectors(self) -> None:
        self.assertEqual(
            self._decode([PHYSICAL_SABM, PHYSICAL_I_N, PHYSICAL_I_MH]),
            [PHYSICAL_SABM, PHYSICAL_I_N, PHYSICAL_I_MH],
        )

    def test_chunk_boundaries_do_not_change_decode(self) -> None:
        self.assertEqual(self._decode([PHYSICAL_I_N], chunk=1), [PHYSICAL_I_N])
        self.assertEqual(self._decode([PHYSICAL_I_N], chunk=120), [PHYSICAL_I_N])

    def test_identical_frames_at_separate_times_remain_separate(self) -> None:
        self.assertEqual(
            self._decode([PHYSICAL_I_N, PHYSICAL_I_N]),
            [PHYSICAL_I_N, PHYSICAL_I_N],
        )

    def test_no_finish_backlog(self) -> None:
        selectors = frame_to_selectors(PHYSICAL_I_N, pre_flags=20, post_flags=3)
        decoder = StreamingBell202Decoder(
            bauds=(1200.0,),
            phases=(0.0, 1.0, 2.0, 3.0),
        )
        decoder.feed(pack(synthesize(selectors)))
        self.assertEqual(decoder.finish(), [])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StreamingRXTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("BELL202_STREAMING_RX_PORT=PASS")
    print("METRIC_TABLE_PATTERNS=4096")
    print("DEFAULT_HYPOTHESES=144")
    print("QUALIFIED_PHYSICAL_FRAME_VECTORS=3")
    print("CHUNK_BOUNDARY_INVARIANCE=PASS")
    print("DSP_FINISH_BACKLOG=NONE")
    print("OVERLAPPING_WINDOW_SEARCH=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
