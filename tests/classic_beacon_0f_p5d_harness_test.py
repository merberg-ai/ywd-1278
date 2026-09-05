#!/usr/bin/env python3
"""Host-only regression for the guarded P5d physical harness."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import qualify_0f_p5d_beacon as p5d  # noqa: E402


class ClassicBeaconP5dHarnessTests(unittest.TestCase):
    def test_fixed_vector_and_authorization_are_exact(self) -> None:
        self.assertEqual(p5d.DESTINATION, "BEACON")
        self.assertEqual(p5d.INFORMATION, "YWD-1278 0F-P5D BEACON 1/1")
        self.assertEqual(p5d.INTERVAL_SECONDS, 10)
        self.assertEqual(p5d.AUTHORIZATION_TOKEN, "0F-P5D-BEACON-145050-ONE")
        self.assertEqual(p5d.ARM_PHRASE, "TRANSMIT-0F-P5D-BEACON-ONE")
        self.assertEqual(p5d.EXTERNAL_PHRASE, "EXTERNAL-BEACON-DECODE-MATCH-ONE")
        self.assertEqual(
            p5d.expected_external_decode(),
            "KJ6YWD-10>BEACON:YWD-1278 0F-P5D BEACON 1/1",
        )

    def test_temporary_config_is_runtime_only(self) -> None:
        original = '''[radio]\ntx_power = 64\ntx_enabled = false\n\n[kiss]\nport = 8001\n\n[console]\nport = 8010\npty_link = "/run/ywd-1278/tnc"\n'''
        changed = p5d.make_temporary_tx_config(original)
        self.assertIn("tx_power = 200", changed)
        self.assertIn("tx_enabled = true", changed)
        self.assertIn("port = 18201", changed)
        self.assertIn("port = 18210", changed)
        self.assertIn('/run/ywd-1278-0f-p5d/tnc', changed)
        self.assertIn("tx_enabled = false", original)

    def test_plan_declares_bounded_safety_contract(self) -> None:
        capture = io.StringIO()
        with redirect_stdout(capture):
            p5d.print_plan()
        text = capture.getvalue()
        for marker in (
            "TX_FREQUENCY_HZ=145050000",
            "TX_POWER=200",
            "BEACON_INTERVAL_SECONDS=10",
            "SCHEDULED_BEACON_EVENTS_MAX=1",
            "INTERNAL_TX_DISPATCHES_MAX=1",
            "AUTOMATIC_TX_RETRY=NO",
            "BEACON_OFF_AFTER_FIRST_DISPATCH=REQUIRED",
            "PERSISTENT_CONFIG_MUTATED=NO",
            "CONNECTED_MODE_TX=NO",
            "FLASH_WRITTEN=NO",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_frozen_host_capability_blobs_are_exact(self) -> None:
        p5d.validate_frozen_capability_blobs()
        self.assertEqual(
            p5d.EXPECTED_HOST_COMMIT,
            "9c9dd3ad30a872b66c7a71e5239c9d85d8948be6",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
