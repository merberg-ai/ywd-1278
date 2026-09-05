#!/usr/bin/env python3
"""Architecture contract for 0F-P5c scheduler safety."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN_P5B = {
    "src/ywd1278/service/classic_beacon.py": "8e1173a58545d3eb88d7afdd839c0746ba53fd2f",
    "tests/product_classic_beacon_0f_p5b_test.py": "ac34b0e3164fd761c27a2e286eec214779522e42",
    "tests/product_classic_beacon_0f_p5b_contract_test.py": "4e5c7486a4d789b43e2ab972836b1b2444260e7f",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductBeaconSchedulerP5cContractTests(unittest.TestCase):
    def test_p5b_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN_P5B.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_single_worker_and_stop_disarm_are_explicit(self) -> None:
        text = (ROOT / "src/ywd1278/service/beacon_scheduler.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("threading.Thread("), 1)
        self.assertIn('name="ywd1278-beacon-scheduler"', text)
        self.assertIn("self._stop_event.wait(self._poll_interval)", text)
        self.assertIn("thread.join(join_timeout_seconds)", text)
        self.assertLess(text.index("thread.join(join_timeout_seconds)"), text.index("self._coordinator.off()", text.index("def stop")))
        self.assertIn("beacon scheduler already running", text)

    def test_no_hardware_or_second_tx_graph(self) -> None:
        text = (ROOT / "src/ywd1278/service/beacon_scheduler.py").read_text(encoding="utf-8")
        for forbidden in (
            "KISSMessage(", "reject_client_message", "TXModemOwner(",
            "PosixSerialTransport(", "ShadowChannelAccessAttempt(", "RPi.GPIO",
        ):
            self.assertNotIn(forbidden, text)
        self.assertFalse((ROOT / "scripts/qualify-0f-p5-beacon-rf.sh").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
