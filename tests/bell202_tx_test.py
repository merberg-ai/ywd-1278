#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, verify_fcs  # noqa: E402
from ywd1278.phy import (  # noqa: E402
    MARK,
    byte_bits_lsb,
    duration_seconds,
    flag_bits,
    frame_to_selectors,
    hdlc_bits,
    nrzi_decode,
    nrzi_encode,
    pack_selectors,
    stuff_bits,
    unpack_selectors,
    unstuff_bits,
)


class Bell202TXTests(unittest.TestCase):
    def test_flag_lsb_order(self) -> None:
        self.assertEqual(flag_bits(), [0, 1, 1, 1, 1, 1, 1, 0])

    def test_bit_stuff_round_trip(self) -> None:
        raw = [1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0]
        stuffed = stuff_bits(raw)
        self.assertEqual(stuffed[:7], [1, 1, 1, 1, 1, 0, 1])
        self.assertEqual(unstuff_bits(stuffed), raw)

    def test_invalid_stuffing_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid HDLC bit stuffing"):
            unstuff_bits([1, 1, 1, 1, 1, 1])

    def test_nrzi_round_trip(self) -> None:
        bits = [0, 1, 1, 0, 0, 1, 0, 1]
        selectors = nrzi_encode(bits, initial_tone=MARK)
        self.assertEqual(nrzi_decode(selectors, initial_tone=MARK), bits)

    def test_selector_pack_round_trip(self) -> None:
        selectors = [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1]
        packed = pack_selectors(selectors)
        self.assertEqual(unpack_selectors(packed, len(selectors)), selectors)

    def test_real_ax25_frame_burst_round_trip(self) -> None:
        frame = build_ui_frame(
            source=Address.parse("KJ6YWD-10"),
            destination=Address.parse("APYWD1"),
            info=b"YWD AX25 1200 TEST",
            include_fcs=True,
        )
        self.assertTrue(verify_fcs(frame))
        body = byte_bits_lsb(frame)
        burst = hdlc_bits(frame, pre_flags=2, post_flags=2)
        self.assertEqual(burst[:16], flag_bits() * 2)
        self.assertEqual(burst[-16:], flag_bits() * 2)
        self.assertEqual(unstuff_bits(burst[16:-16]), body)

    def test_default_txdelay_is_300ms_of_flags(self) -> None:
        frame = build_ui_frame(
            source=Address.parse("KJ6YWD-10"),
            destination=Address.parse("APYWD1"),
            info=b"X",
            include_fcs=True,
        )
        selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3)
        self.assertGreater(duration_seconds(len(selectors)), 0.32)
        self.assertLess(duration_seconds(len(selectors)), 0.8)

    def test_ax25_5b_physically_qualified_selector_equivalence(self) -> None:
        # This exact ordinary KISS-originated frame was independently decoded
        # over RF during the frozen AX25-5B qualification as:
        #   KJ6YWD-10>APYWD1: AX25-5B KISS TX TEST
        # The qualified YWD-MMDVM host reported exactly 691 Bell-202 selectors,
        # expanded by the STM32 to 11056 samples (691 * 16).
        frame = build_ui_frame(
            source=Address.parse("KJ6YWD-10"),
            destination=Address.parse("APYWD1"),
            info=b"AX25-5B KISS TX TEST",
            include_fcs=True,
        )
        self.assertEqual(
            frame.hex(),
            "82a0b2ae8862e096946cb2ae887503f0415832352d3542204b4953532054582054455354f8ff",
        )
        self.assertTrue(verify_fcs(frame))

        selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3, initial_tone=MARK)
        self.assertEqual(len(selectors), 691)
        self.assertAlmostEqual(duration_seconds(len(selectors)), 691 / 1200.0)

        packed = pack_selectors(selectors)
        self.assertEqual(len(packed), 87)
        self.assertEqual(
            hashlib.sha256(packed).hexdigest(),
            "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e",
        )
        self.assertEqual(unpack_selectors(packed, 691), selectors)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Bell202TXTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("BELL202_TX_SERIALIZER_PORT=PASS")
    print("HDLC_BIT_STUFFING=PASS")
    print("AX25_NRZI=PASS")
    print("SELECTOR_PACKING=PASS")
    print("AX25_5B_SELECTOR_COUNT=691")
    print("AX25_5B_SELECTOR_PACKED_SHA256=30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
