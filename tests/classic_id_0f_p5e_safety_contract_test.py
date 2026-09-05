#!/usr/bin/env python3
"""Static authorization and one-shot safety contract for P5e ID."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_0f_p5e_id.py"


class ClassicIDP5eSafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_transmit_requires_token_firmware_root_and_interactive_arm(self) -> None:
        for marker in (
            'if not args.transmit:', 'if os.geteuid() != 0:',
            'args.authorize != AUTHORIZATION_TOKEN', 'if args.firmware is None:',
            'typed = input(', 'if typed != ARM_PHRASE:',
        ):
            self.assertIn(marker, self.text)

    def test_exactly_one_manual_id_command_and_no_beacon_arm(self) -> None:
        command = 'reply = console_command(console, "ID")'
        self.assertEqual(self.text.count(command), 1)
        self.assertIn('wait_for_one_dispatch(console)', self.text)
        self.assertIn('NO_DUPLICATE_HOLD_SECONDS = 2.0', self.text)
        for forbidden in ('"BEACON EVERY', '"BTEXT ', '"UNPROTO ', '"CONVERSE"'):
            self.assertNotIn(forbidden, self.text)

    def test_no_kiss_tx_firmware_write_or_automatic_retry(self) -> None:
        for forbidden in (
            "KISSMessage(port=0, command=DATA", "stm32flash -w", "--write",
            "automatic retry",
        ):
            self.assertNotIn(forbidden, self.text)
        self.assertIn("stage_i._check_firmware(args.firmware)", self.text)
        self.assertIn("stage_i._verify_eligibility(args.firmware)", self.text)
        self.assertIn("stage_i._restore_service(original_hash)", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
