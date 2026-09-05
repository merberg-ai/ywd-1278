#!/usr/bin/env python3
"""Static and dry-run safety contract for the 0G-P6 RF harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_0g_p6_connected.py"


class ConnectedPhysicalP6SafetyTests(unittest.TestCase):
    def test_dry_run_is_inert_and_declares_exact_scope(self) -> None:
        run = subprocess.run(
            [sys.executable, str(HARNESS)], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
        )
        for marker in (
            "REMOTE_NODE=KJ6YWD-5", "REMOTE_ALIAS=YWDNOD",
            "INFORMATION_FRAMES_NEW_MAX=1", "ORDERLY_DISC_REQUIRED=YES",
            "YWD1278_0G_P6_DRY_RUN=PASS", "SERVICE_MUTATED=NO",
            "MODEM_UART_OPENED=NO", "RF_TRANSMITTED=NO",
        ):
            self.assertIn(marker, run.stdout)

    def test_physical_path_is_triply_gated_and_restores_service(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        for marker in (
            'AUTHORIZATION_TOKEN = "0G-P6-CONNECTED-145050-KJ6YWD5-ONE"',
            'ARM_PHRASE = "TRANSMIT-0G-P6-CONNECTED-KJ6YWD-5-ONE"',
            "if os.geteuid() != 0:", "stage_i._check_firmware(args.firmware)",
            "stage_i._verify_eligibility(args.firmware)",
            "stage_i._restore_service(original_hash)",
            "persistent config changed during P6",
        ):
            self.assertIn(marker, text)

    def test_harness_uses_public_p5_and_kiss_boundaries(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        for marker in (
            "ConnectedSessionManager(", "manager.execute_line(",
            "manager.handle_frame(", "manager.poll(",
            "encode(action.frame_no_fcs, port=0, command=DATA)",
        ):
            self.assertIn(marker, text)
        for forbidden in ("manager._sessions", "._link", "TXModemOwner(", "PosixSerialTransport("):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
