#!/usr/bin/env python3
"""Static authorization and one-event safety contract for P5d."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_0f_p5d_beacon.py"


class ClassicBeaconP5dSafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_transmit_requires_token_firmware_root_and_interactive_arm(self) -> None:
        for marker in (
            'if not args.transmit:',
            'if os.geteuid() != 0:',
            'args.authorize != AUTHORIZATION_TOKEN',
            'if args.firmware is None:',
            'typed = input(',
            'if typed != ARM_PHRASE:',
        ):
            self.assertIn(marker, self.text)

    def test_only_one_arm_and_mandatory_off_follow_dispatch(self) -> None:
        arm = 'console_command(console, f"BEACON EVERY {INTERVAL_SECONDS}")'
        off = 'console_command(console, "BEACON OFF")'
        wait = "wait_for_one_dispatch(console)"
        self.assertEqual(self.text.count(arm), 1)
        self.assertEqual(self.text.count(off), 1)
        self.assertLess(self.text.index(arm), self.text.index(wait))
        self.assertLess(self.text.index(wait), self.text.index(off))
        self.assertIn("NO_DUPLICATE_HOLD_SECONDS = 12.0", self.text)
        self.assertNotIn('console_command(console, "CONVERSE")', self.text)

    def test_no_kiss_tx_firmware_write_or_automatic_retry(self) -> None:
        for forbidden in (
            "KISSMessage(port=0, command=DATA",
            "stm32flash -w",
            "--write",
            "automatic retry",
        ):
            self.assertNotIn(forbidden, self.text)
        self.assertIn("stage_i._check_firmware(args.firmware)", self.text)
        self.assertIn("stage_i._verify_eligibility(args.firmware)", self.text)
        self.assertIn("stage_i._restore_service(original_hash)", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
