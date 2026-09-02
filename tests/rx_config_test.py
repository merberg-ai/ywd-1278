from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.rx_config import (  # noqa: E402
    RX_MODEM_IO_CONFIG,
    arm_rx_modem_io_request,
    set_rx_frequency_request,
    validate_rx_frequency_hz,
)


class RXConfigTests(unittest.TestCase):
    def test_aprs_frequency_request_matches_frozen_mmdvm_layout(self) -> None:
        request = set_rx_frequency_request(144_390_000)
        self.assertEqual(
            request,
            bytes.fromhex("e0 0d 04 00 70 37 9b 08 70 37 9b 08 01"),
        )
        frame = protocol.parse_frame(request, expected_command=protocol.SET_FREQ)
        self.assertEqual(len(frame.payload), 10)
        self.assertEqual(frame.payload[0], 0)
        self.assertEqual(frame.payload[-1], 1)

    def test_fixed_rx_safe_modem_io_profile_is_bit_exact(self) -> None:
        self.assertEqual(
            RX_MODEM_IO_CONFIG,
            bytes.fromhex("80 02 00 00 00 78 01 00 00 32 32 32 32"),
        )
        self.assertEqual(
            arm_rx_modem_io_request(),
            bytes.fromhex("e0 10 02 80 02 00 00 00 78 01 00 00 32 32 32 32"),
        )

    def test_frequency_guards_match_frozen_capture_rules(self) -> None:
        for valid in (144_390_000, 223_500_000, 446_000_000, 915_000_000):
            self.assertEqual(validate_rx_frequency_hz(valid), valid)

        for invalid in (143_999_999, 148_000_000, 145_900_000, 436_000_000, 1_000_000_000):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_rx_frequency_hz(invalid)

    def test_setup_module_has_no_packet_tx_builder(self) -> None:
        import ywd1278.modem.rx_config as module

        names = set(dir(module))
        self.assertNotIn("rf_tx_tones_request", names)
        self.assertNotIn("TX_TONES", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
