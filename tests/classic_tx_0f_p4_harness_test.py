#!/usr/bin/env python3
"""Host-only regression tests for the 0F-P4 physical qualification harness."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import qualify_0f_p4_classic_tx as p4  # noqa: E402


class ClassicTX0FP4HarnessTests(unittest.TestCase):
    def test_fixed_operator_vector_is_direct_and_single_shot(self) -> None:
        self.assertEqual(p4.DESTINATION, "YWD127")
        self.assertEqual(p4.INFORMATION, "YWD-1278 0F-P4 CLASSIC TX 1/1")
        self.assertEqual(
            p4.expected_external_decode(),
            "KJ6YWD-10>YWD127:YWD-1278 0F-P4 CLASSIC TX 1/1",
        )
        self.assertEqual(p4.AUTHORIZATION_TOKEN, "0F-P4-TX-145050-ONE")
        self.assertEqual(p4.ARM_PHRASE, "TRANSMIT-0F-P4-ONE")
        self.assertEqual(p4.EXTERNAL_PHRASE, "EXTERNAL-DECODE-MATCH-ONE")

    def test_temporary_config_changes_only_qualified_runtime_controls(self) -> None:
        original = '''[radio]\ntx_power = 64\ntx_enabled = false\n\n[kiss]\nport = 8001\n\n[console]\nport = 8010\npty_link = "/run/ywd-1278/tnc"\n'''
        changed = p4.make_temporary_tx_config(original)
        self.assertIn("tx_power = 200", changed)
        self.assertIn("tx_enabled = true", changed)
        self.assertIn("port = 18101", changed)
        self.assertIn("port = 18110", changed)
        self.assertIn('pty_link = "/run/ywd-1278-0f-p4/tnc"', changed)
        self.assertIn("tx_power = 64", original)
        self.assertIn("tx_enabled = false", original)
        self.assertNotEqual(changed, original)

    def test_print_plan_declares_all_hard_limits(self) -> None:
        capture = io.StringIO()
        with redirect_stdout(capture):
            p4.print_plan()
        text = capture.getvalue()
        for marker in (
            "TX_FREQUENCY_HZ=145050000",
            "TX_POWER=200",
            "TX_ORIGIN=CLASSIC_TELNET_CONVERSE",
            "CLASSIC_CONVERSE_TX_LINES_MAX=1",
            "KISS_TX_MESSAGES=0",
            "INTERNAL_TX_DISPATCHES_MAX=1",
            "AUTOMATIC_TX_RETRY=NO",
            "PERSISTENT_CONFIG_MUTATED=NO",
            "BEACON_TX=NO",
            "CONNECTED_MODE_TX=NO",
            "FLASH_WRITTEN=NO",
            "OPTION_BYTES_WRITTEN=NO",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_host_qualified_capability_blobs_are_still_exact(self) -> None:
        p4.validate_frozen_capability_blobs()
        self.assertEqual(
            p4.HOST_QUALIFIED_CHECKPOINT,
            "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
