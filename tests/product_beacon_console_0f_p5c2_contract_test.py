#!/usr/bin/env python3
"""Architecture contract for shared P5c2 daemon/console integration."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/service/classic_beacon.py": "8e1173a58545d3eb88d7afdd839c0746ba53fd2f",
    "src/ywd1278/service/beacon_scheduler.py": "2dab60bdb6289b1f5fbe90a004e7d371f45d7451",
    "tests/product_beacon_scheduler_0f_p5c_test.py": "7ab296efee5b84b849b49580c2124ff63b4a9455",
    "tests/product_beacon_scheduler_0f_p5c_contract_test.py": "7123800343743263f416c57a9d6b2ac77bcfa813",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductBeaconConsoleP5c2ContractTests(unittest.TestCase):
    def test_p5c_and_lower_owners_are_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_console_and_scheduler_share_one_coordinator(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertEqual(daemon.count("ThreadSafeProductBeaconCoordinator("), 1)
        self.assertIn("ProductBeaconScheduler(\n            beacon,", daemon)
        self.assertIn("beacon=beacon", daemon)
        self.assertLess(daemon.index("console.stop()"), daemon.index("beacon_scheduler.stop()"))
        self.assertLess(daemon.index("beacon_scheduler.stop()"), daemon.index("engine.stop()"))

    def test_existing_submitter_is_reused_and_persistent_beacon_stays_forbidden(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertEqual(daemon.count("make_product_backend_submitter("), 1)
        appliance = (ROOT / "src/ywd1278/service/appliance.py").read_text(encoding="utf-8")
        self.assertIn('raise ProductConfigurationError("beacon.enabled requires future 0F qualification")', appliance)
        self.assertFalse((ROOT / "scripts/qualify-0f-p5-beacon-rf.sh").exists())

    def test_new_console_layer_has_no_hardware_or_second_tx_graph(self) -> None:
        text = (ROOT / "src/ywd1278/service/product_beacon_console.py").read_text(encoding="utf-8")
        for forbidden in (
            "KISSMessage(", "reject_client_message", "TXModemOwner(",
            "PosixSerialTransport(", "ShadowChannelAccessAttempt(", "RPi.GPIO",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
