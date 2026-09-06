#!/usr/bin/env python3
"""Pre-RF contract for guarded 0H-P10 LinBPQ delivery qualification."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_0h_p10_linbpq_delivery.py"

FROZEN = {
    "src/ywd1278/node/linbpq_dialogue.py": "6c3776b7ffe92cb6216c682fc7c12081c57d12aa",
    "src/ywd1278/node/forwarding_integration.py": "263b5583d473a5673e6dfa60978804055197f676",
    "tools/qualify_0h_p7_mailbox.py": "b9ba6c07a210a946e5988cb051b5a7c6f6ca9635",
    "firmware/qualification/0h-p7-mailbox-target-pi.json": "365fabbaa6a6dd2bce703cd35c83e96d4dbad3c8",
}


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class LinBPQDeliveryP10ContractTests(unittest.TestCase):
    def test_frozen_p9_p8_p7_lineage(self) -> None:
        for path, expected in FROZEN.items():
            self.assertEqual(blob(ROOT / path), expected, path)

    def test_harness_is_explicitly_one_session_and_guarded(self) -> None:
        text = HARNESS.read_text()
        for marker in (
            'EXPECTED_HOST_COMMIT = "618585fd2588235296a281022cf39feb5f2ba8e9"',
            'AUTHORIZATION_TOKEN = "0H-P10-LINBPQ-145050-KJ6YWD5-ONE"',
            'ARM_PHRASE = "TRANSMIT-0H-P10-LINBPQ-KJ6YWD-5-ONE"',
            'REMOTE_LISTENER = Address.parse("KJ6YWD-5")',
            'BBS = Address.parse("KJ6YWD-1")',
            'DESTINATION = Address.parse("KJ6YWD-15")',
            'BBS_ENTRY = b"BBS\\r"',
            'SUBJECT = "P10 TEST"',
            'ONE_MESSAGE_MAX=YES',
            'AUTOMATIC_RETRY_OF_MESSAGE=NO',
            'tx_enabled", "true"',
            'frequency_hz != stage_i.EXPECTED_FREQUENCY_HZ',
            'dialogue.snapshot.state is LinBPQState.COMPLETE',
            'link.snapshot.link.outstanding == 0',
            'link.disconnect(now=time.monotonic())',
            'stage_i._restore_service(original_hash)',
        ):
            self.assertIn(marker, text)
        for forbidden in (
            "MailboxStore(",
            "prepare_batch(",
            "schedule.",
            "threading",
            "os.system(",
        ):
            self.assertNotIn(forbidden, text)

    def test_no_runtime_wiring(self) -> None:
        for path in ("src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py"):
            self.assertNotIn(
                "qualify_0h_p10_linbpq_delivery",
                (ROOT / path).read_text(),
            )

    def test_dry_run_cannot_touch_rf(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HARNESS)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("YWD1278_0H_P10_DRY_RUN=PASS", result.stdout)
        self.assertIn("SERVICE_MUTATED=NO", result.stdout)
        self.assertIn("MODEM_UART_OPENED=NO", result.stdout)
        self.assertIn("RF_TRANSMITTED=NO", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
