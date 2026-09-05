#!/usr/bin/env python3
"""Host-only regression for the guarded P5e physical ID harness."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import qualify_0f_p5e_id as p5e  # noqa: E402


class ClassicIDP5eHarnessTests(unittest.TestCase):
    def test_fixed_vector_and_authorization_are_exact(self) -> None:
        self.assertEqual(p5e.DESTINATION, "ID")
        self.assertEqual(p5e.INFORMATION_PREFIX, "YWD-1278 ID ")
        self.assertEqual(p5e.AUTHORIZATION_TOKEN, "0F-P5E-ID-145050-ONE")
        self.assertEqual(p5e.ARM_PHRASE, "TRANSMIT-0F-P5E-ID-ONE")
        self.assertEqual(p5e.EXTERNAL_PHRASE, "EXTERNAL-ID-DECODE-MATCH-ONE")
        self.assertEqual(
            p5e.expected_external_decode(),
            "KJ6YWD-10>ID:YWD-1278 ID KJ6YWD-10",
        )

    def test_temporary_config_is_runtime_only(self) -> None:
        original = '''[radio]\ntx_power = 64\ntx_enabled = false\n\n[kiss]\nport = 8001\n\n[console]\nport = 8010\npty_link = "/run/ywd-1278/tnc"\n'''
        changed = p5e.make_temporary_tx_config(original)
        self.assertIn("tx_power = 200", changed)
        self.assertIn("tx_enabled = true", changed)
        self.assertIn("port = 18201", changed)
        self.assertIn("port = 18210", changed)
        self.assertIn('/run/ywd-1278-0f-p5e/tnc', changed)
        self.assertIn("tx_enabled = false", original)

    def test_plan_declares_bounded_safety_contract(self) -> None:
        capture = io.StringIO()
        with redirect_stdout(capture):
            p5e.print_plan()
        text = capture.getvalue()
        for marker in (
            "TX_FREQUENCY_HZ=145050000", "TX_POWER=200",
            "MANUAL_ID_COMMANDS_MAX=1", "INTERNAL_TX_DISPATCHES_MAX=1",
            "AUTOMATIC_TX_RETRY=NO", "BEACON_SCHEDULER_USED=NO",
            "PERSISTENT_CONFIG_MUTATED=NO", "CONNECTED_MODE_TX=NO",
            "FLASH_WRITTEN=NO",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_frozen_host_capability_blobs_are_exact(self) -> None:
        p5e.validate_frozen_capability_blobs()
        self.assertEqual(
            p5e.EXPECTED_HOST_COMMIT,
            "79c249167902256399070482d773b39bda96fdea",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
