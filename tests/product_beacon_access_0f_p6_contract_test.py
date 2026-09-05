#!/usr/bin/env python3
"""Architecture and lineage contract for 0F-P6 beacon access policy."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/service/classic_beacon.py": "8e1173a58545d3eb88d7afdd839c0746ba53fd2f",
    "src/ywd1278/service/beacon_scheduler.py": "2dab60bdb6289b1f5fbe90a004e7d371f45d7451",
    "src/ywd1278/service/product_beacon_console.py": "5b21ba853c978e9c3e268e47ca6fb24a7f6aa081",
    "src/ywd1278/service/product_id_console.py": "befcfb31fb4115ff6219a1b95d2449a522f05a9f",
    "tools/qualify_0f_p5e_id.py": "bf3ab5aeacc6701d2b9302660ef2cedc58a85ba2",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
    "tests/classic_id_0f_p5e_physical_evidence_contract_test.py": "2513bde062ffb272055fa0a5aec21ab5b2dba7aa",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductBeaconAccessP6ContractTests(unittest.TestCase):
    def test_p5e_and_lower_owners_are_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_policy_only_delegates_to_frozen_coordinator(self) -> None:
        text = (ROOT / "src/ywd1278/service/beacon_access_policy.py").read_text(encoding="utf-8")
        self.assertIn("class JitteredThreadSafeProductBeaconCoordinator(", text)
        self.assertEqual(text.count("result = super().tick(now=now)"), 1)
        self.assertIn("MAX_JITTER_SECONDS = 60.0", text)
        self.assertIn("JITTER_FRACTION = 0.10", text)
        self.assertIn("super().off()", text)

    def test_policy_has_no_queue_csma_hardware_or_retry_implementation(self) -> None:
        text = (ROOT / "src/ywd1278/service/beacon_access_policy.py").read_text(encoding="utf-8")
        for forbidden in (
            "KISSMessage(", "reject_client_message", "ThreadSafeKISSDataAdmissionQueue(",
            "PersistentCSMA(", "TXModemOwner(", "PosixSerialTransport(",
            "ShadowChannelAccessAttempt(", "RPi.GPIO", "time.sleep(",
        ):
            self.assertNotIn(forbidden, text)

    def test_daemon_has_one_submitter_and_selects_p6_coordinator(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertEqual(daemon.count("make_product_backend_submitter("), 1)
        self.assertEqual(daemon.count("JitteredThreadSafeProductBeaconCoordinator("), 1)
        self.assertIn("tx_submitter=submitter", daemon)
        self.assertIn("ProductBeaconScheduler(\n            beacon,", daemon)


if __name__ == "__main__":
    unittest.main(verbosity=2)
