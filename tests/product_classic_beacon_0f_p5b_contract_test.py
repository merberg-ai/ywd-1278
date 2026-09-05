#!/usr/bin/env python3
"""Architecture contract for 0F-P5b host product composition."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/console/classic_beacon.py": "26b69b2272bf9277cff80e8dfc6c62465e378dad",
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/daemon.py": "ce1ba6af92f7238ab1a1ac0aca268a94c4fa515b",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductClassicBeaconP5bContractTests(unittest.TestCase):
    def test_p5a_and_product_boundaries_are_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_only_existing_submit_contract_is_used(self) -> None:
        text = (ROOT / "src/ywd1278/service/classic_beacon.py").read_text(encoding="utf-8")
        self.assertIn("ClassicTXSubmitter", text)
        self.assertIn("self._tx_submitter(frame_no_fcs)", text)
        self.assertIn("include_fcs=False", text)
        for forbidden in (
            "KISSMessage(", "reject_client_message", "KISSDataAdmissionQueue(",
            "TXModemOwner(", "ShadowChannelAccessAttempt(", "PosixSerialTransport(",
            "Thread(", "Timer(", "sleep(", "while True",
        ):
            self.assertNotIn(forbidden, text)

    def test_daemon_and_physical_boundaries_remain_absent(self) -> None:
        self.assertFalse((ROOT / "scripts/qualify-0f-p5-beacon-rf.sh").exists())
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertNotIn("ProductBeaconCoordinator", daemon)


if __name__ == "__main__":
    unittest.main(verbosity=2)
