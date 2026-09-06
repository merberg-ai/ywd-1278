#!/usr/bin/env python3
"""Safety contract for the staged 0F-P8 converse qualifier."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

import qualify_0f_p8_sustained_converse as p8

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/qualify_0f_p8_sustained_converse.py"


class P8PhysicalStagingContractTests(unittest.TestCase):
    def test_plan_is_bounded_to_requested_unproto_state(self) -> None:
        self.assertEqual(p8.DESTINATION, "JIM")
        self.assertEqual(p8.PATH, ("YWDNOD",))
        self.assertEqual(len(p8.INFORMATION), 3)
        self.assertEqual(len(set(p8.INFORMATION)), 3)
        self.assertEqual(p8.stage_i.EXPECTED_FREQUENCY_HZ, 145_050_000)

        out = StringIO()
        with redirect_stdout(out):
            p8.print_plan()
        plan = out.getvalue()
        self.assertIn("UNPROTO_DESTINATION=JIM", plan)
        self.assertIn("UNPROTO_PATH=YWDNOD", plan)
        self.assertIn("CLASSIC_CONVERSE_TX_LINES_MAX=3", plan)
        self.assertIn("LIVE_RX_REQUIRED_IN_SAME_SESSION=YES", plan)
        self.assertIn("CTRL_C_ESCAPE=REQUIRED_NO_TX", plan)
        self.assertIn("CTRL_C_PARTIAL_LINE_DISCARD=REQUIRED", plan)
        self.assertIn("AUTOMATIC_TX_RETRY=NO", plan)
        self.assertIn("PERSISTENT_TX_ENABLED=NO", plan)
        self.assertIn("FLASH_WRITTEN=NO", plan)
        self.assertIn("OPTION_BYTES_WRITTEN=NO", plan)

    def test_exact_expected_monitor_lines_include_via_path(self) -> None:
        expected = [
            "KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 1/3",
            "KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 2/3",
            "KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE 3/3",
        ]
        actual = [p8.expected_external_decode(line) for line in p8.INFORMATION]
        self.assertEqual(actual, expected)

    def test_current_product_runtime_is_blob_pinned(self) -> None:
        self.assertEqual(
            p8.FROZEN_P8_BLOBS["src/ywd1278/console/product_session.py"],
            "21528919b0014c75ce98fff328b8c0830e6925b9",
        )
        p8.validate_product_blobs()

    def test_source_keeps_staging_and_restore_guards(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertIn("stage_i._restore_service(original_hash)", text)
        self.assertIn("PERSISTENT_CONFIG_MUTATED=NO", text)
        self.assertIn("INSTALLED_SOURCE_MUTATED=NO", text)
        self.assertIn("NORMAL_SERVICE_RESTORED=YES", text)
        self.assertIn("CTRL_C_ADDITIONAL_TX=0", text)
        self.assertIn("assert_tx_status(final, 3)", text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("git checkout", text)
        self.assertNotIn("git pull", text)
        self.assertNotIn("stm32flash", text.lower())
        self.assertNotIn("deploy-product-firmware", text.lower())

    def test_qualifier_has_no_direct_kiss_or_frame_builder_import(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("ywd1278.kiss", text)
        self.assertNotIn("KISSStreamDecoder", text)
        self.assertNotIn("build_ui_frame", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
