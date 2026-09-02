#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import (  # noqa: E402
    AX25_PID_NO_L3,
    Address,
    append_fcs,
    build_ui_frame,
    crc_x25,
    encode_address,
    parse_frame,
    parse_ui_frame,
    verify_fcs,
)


class AX25CodecTests(unittest.TestCase):
    def test_crc_x25_canonical_vector(self) -> None:
        self.assertEqual(crc_x25(b"123456789"), 0x906E)

    def test_callsign_parser(self) -> None:
        self.assertEqual(Address.parse("kj6ywd-10"), Address("KJ6YWD", 10, False))
        self.assertEqual(str(Address.parse("N0CALL")), "N0CALL")
        with self.assertRaises(ValueError):
            Address.parse("TOOLONG7-1")
        with self.assertRaises(ValueError):
            Address.parse("KJ6YWD-16")
        with self.assertRaises(ValueError):
            Address.parse("BAD CALL")

    def test_ui_frame_round_trip(self) -> None:
        frame = build_ui_frame(
            source=Address.parse("KJ6YWD-10"),
            destination=Address.parse("APYWD1"),
            path=[Address.parse("WIDE1-1")],
            info=b"YWD-1278 AX25 TEST",
            include_fcs=True,
        )
        self.assertTrue(verify_fcs(frame))
        parsed = parse_ui_frame(frame, has_fcs=True)
        self.assertEqual(str(parsed["destination"]), "APYWD1")
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual([str(x) for x in parsed["path"]], ["WIDE1-1"])
        self.assertEqual(parsed["frame_class"], "U")
        self.assertEqual(parsed["frame_type"], "UI")
        self.assertEqual(parsed["pid"], AX25_PID_NO_L3)
        self.assertEqual(parsed["info"], b"YWD-1278 AX25 TEST")

    def test_physical_rx_i_frame_n(self) -> None:
        # Frozen YWD-MMDVM AX25R3 physical capture, 2026-09-01. Direwolf
        # independently decoded the same over-air packet as KJ6YWD-1>RDG:n<CR>.
        frame = bytes.fromhex(
            "a4 88 8e 40 40 40 e0 "
            "96 94 6c b2 ae 88 63 "
            "20 f0 6e 0d 00 28"
        )
        self.assertTrue(verify_fcs(frame))
        parsed = parse_frame(frame, has_fcs=True)
        self.assertEqual(str(parsed["destination"]), "RDG")
        self.assertEqual(str(parsed["source"]), "KJ6YWD-1")
        self.assertEqual(parsed["frame_class"], "I")
        self.assertEqual(parsed["frame_type"], "I")
        self.assertEqual(parsed["control"], 0x20)
        self.assertEqual(parsed["ns"], 0)
        self.assertEqual(parsed["nr"], 1)
        self.assertEqual(parsed["pid"], AX25_PID_NO_L3)
        self.assertEqual(parsed["info"], b"n\r")

    def test_physical_rx_i_frame_mh(self) -> None:
        # Second frozen physical capture; Direwolf decoded KJ6YWD-1>RDG:mh<CR>.
        frame = bytes.fromhex(
            "a4 88 8e 40 40 40 e0 "
            "96 94 6c b2 ae 88 63 "
            "82 f0 6d 68 0d 70 23"
        )
        self.assertTrue(verify_fcs(frame))
        parsed = parse_frame(frame, has_fcs=True)
        self.assertEqual(parsed["frame_class"], "I")
        self.assertEqual(parsed["control"], 0x82)
        self.assertEqual(parsed["ns"], 1)
        self.assertEqual(parsed["nr"], 4)
        self.assertEqual(parsed["pid"], AX25_PID_NO_L3)
        self.assertEqual(parsed["info"], b"mh\r")

    @staticmethod
    def _control_frame(control: int, info: bytes = b"") -> bytes:
        body = bytearray()
        body.extend(encode_address(Address.parse("NODE"), last=False))
        body.extend(encode_address(Address.parse("N0CALL-2"), last=True))
        body.append(control)
        body.extend(info)
        return append_fcs(bytes(body))

    def test_modulo8_supervisory_rr(self) -> None:
        parsed = parse_frame(self._control_frame(0x61), has_fcs=True)
        self.assertEqual(parsed["frame_class"], "S")
        self.assertEqual(parsed["frame_type"], "RR")
        self.assertEqual(parsed["nr"], 3)
        self.assertFalse(parsed["poll_final"])
        self.assertIsNone(parsed["pid"])

    def test_common_unnumbered_frames(self) -> None:
        sabm = parse_frame(self._control_frame(0x2F), has_fcs=True)
        self.assertEqual((sabm["frame_class"], sabm["frame_type"]), ("U", "SABM"))
        self.assertFalse(sabm["poll_final"])

        ua_pf = parse_frame(self._control_frame(0x73), has_fcs=True)
        self.assertEqual((ua_pf["frame_class"], ua_pf["frame_type"]), ("U", "UA"))
        self.assertTrue(ua_pf["poll_final"])

    def test_bad_fcs_rejected(self) -> None:
        frame = build_ui_frame(
            source=Address.parse("N0CALL"),
            destination=Address.parse("TEST"),
            info=b"bad-fcs-check",
            include_fcs=True,
        )
        damaged = frame[:-1] + bytes([frame[-1] ^ 0x01])
        self.assertFalse(verify_fcs(damaged))
        with self.assertRaisesRegex(ValueError, "bad AX.25 FCS"):
            parse_frame(damaged, has_fcs=True)

    def test_ui_without_fcs_for_future_kiss_boundary(self) -> None:
        no_fcs = build_ui_frame(
            source=Address.parse("N0CALL"),
            destination=Address.parse("APYWD1"),
            info=b"NO FCS",
            include_fcs=False,
        )
        self.assertFalse(verify_fcs(no_fcs))
        parsed = parse_ui_frame(no_fcs, has_fcs=False)
        self.assertEqual(parsed["info"], b"NO FCS")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AX25CodecTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("AX25_CODEC_PORT=PASS")
    print("AX25_FCS_VECTOR=PASS")
    print("AX25_PHYSICAL_CAPTURE_VECTORS=PASS")
    print("AX25_MOD8_I_S_U_PARSER=PASS")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
