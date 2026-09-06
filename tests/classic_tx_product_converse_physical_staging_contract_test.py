#!/usr/bin/env python3
"""Host/static safety contract for the product-converse physical qualifier."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/qualify_0f_product_converse.py"


class ProductConversePhysicalStagingContractTests(unittest.TestCase):
    def test_default_dry_run_has_explicit_zero_io_markers(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tools")))
        proc = subprocess.run(
            [sys.executable, str(TOOL)],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        out = proc.stdout
        self.assertIn("YWD1278_0F_PRODUCT_CONVERSE_DRY_RUN=PASS", out)
        self.assertIn("SERVICE_MUTATED=NO", out)
        self.assertIn("MODEM_UART_OPENED=NO", out)
        self.assertIn("CONVERSE_TX_LINE_SENT=NO", out)
        self.assertIn("RF_TRANSMITTED=NO", out)

    def test_physical_path_is_one_shot_and_restores_persistent_baseline(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertIn('AUTHORIZATION_TOKEN = "0F-PRODUCT-CONVERSE-TX-145050-ONE"', text)
        self.assertIn('ARM_PHRASE = "TRANSMIT-0F-PRODUCT-CONVERSE-ONE"', text)
        self.assertIn('INFORMATION = "YWD-1278 PRODUCT CONVERSE 1/1"', text)
        self.assertEqual(text.count("send_one_converse_line(console)"), 1)
        self.assertIn("stage_i.assert_single_shot_status(status, require_dispatched=True)", text)
        self.assertIn("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS", text)
        self.assertIn("stage_i._restore_service(original_hash)", text)
        self.assertIn("PERSISTENT_CONFIG_MUTATED=NO", text)
        self.assertIn("INSTALLED_SOURCE_MUTATED=NO", text)
        self.assertIn("OPTION_BYTES_WRITTEN=NO", text)
        self.assertNotIn("stm32flash", text)
        self.assertNotIn("deploy-product-firmware", text)

    def test_product_session_behavior_is_physically_exercised(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertIn('sock.sendall(b"CONVERSE\\r\\n")', text)
        self.assertIn('if "cmd:" in text:', text)
        self.assertIn("LIVE RX DISPLAY ENABLED", text)
        self.assertIn('sock.sendall(b"/CMD\\r\\n")', text)
        self.assertIn("wait_live_rx(console", text)
        self.assertIn("PRODUCT_CONVERSE_LIVE_RX=PASS", text)
        self.assertIn("COMMAND_PROMPT_RESTORED=PASS", text)
        self.assertIn("PRE_CONVERSE_HISTORY_REPLAY=NO", text)

    def test_staged_source_runs_without_mutating_installed_source(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertIn('[sys.executable, "-m", "ywd1278.daemon"', text)
        self.assertIn('env["PYTHONPATH"]', text)
        self.assertIn("INSTALLED_BASELINE_COMMIT=", text)
        self.assertIn("stage_i.INSTALLED_COMMIT.read_text", text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("git checkout", text)
        self.assertNotIn("git pull", text)

    def test_no_kiss_tx_injection_path_is_present(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("KISSStreamDecoder", text)
        self.assertNotIn("kiss.framing", text)
        self.assertNotIn("encode(", text)
        self.assertIn("KISS_TX_MESSAGES=0", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
