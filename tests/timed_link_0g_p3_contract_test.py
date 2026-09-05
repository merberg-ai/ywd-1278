#!/usr/bin/env python3
"""Architecture and preservation contract for host-only 0G-P3 timers."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/link/modulo8.py": "9ebaa1c07923060adbc568d1825ac6bf40a69579",
    "src/ywd1278/link/data_link.py": "40e9fde0df520d43938c12e817c420588d1e5463",
    "tests/modulo8_data_link_0g_p2_test.py": "8b2d9ca78501ac9103c326149b194bccfd4a8101",
    "tests/modulo8_data_link_0g_p2_contract_test.py": "02978da46b3e3d310310e70ac4d51f38cb5d6321",
    "src/ywd1278/daemon.py": "f5ff3c6d9feea4c020d84d13795cfcca40ef186f",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class TimedLinkP3ContractTests(unittest.TestCase):
    def test_p1_p2_and_physical_lineage_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_timer_configuration_and_explicit_clock_are_bounded(self) -> None:
        text = (ROOT / "src/ywd1278/link/timed_link.py").read_text(encoding="utf-8")
        for marker in (
            '("t1_seconds", self.t1_seconds, 0.1, 60.0)',
            '("t2_seconds", self.t2_seconds, 0.01, 10.0)',
            '("t3_seconds", self.t3_seconds, 1.0, 3600.0)',
            'raise ValueError("T2 must be shorter than T1")',
            'raise ValueError("T3 must be longer than T1")',
            'not 0 <= self.max_retries <= 15',
            'def poll(self, *, now: float)',
            'raise ValueError("now must be monotonic")',
        ):
            self.assertIn(marker, text)

    def test_p3_has_no_clock_thread_runtime_or_dispatch_owner(self) -> None:
        text = (ROOT / "src/ywd1278/link/timed_link.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading", "time.sleep(", "socket", "KISSMessage(",
            "reject_client_message", "ProductBeaconScheduler(", "TXModemOwner(",
            "PosixSerialTransport(", "RPi.GPIO", "subprocess", "open(",
            "serial", "modem", "sendall(", "write(",
        ):
            self.assertNotIn(forbidden, text)

    def test_existing_product_owners_do_not_import_p3(self) -> None:
        for relative in (
            "src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py",
            "src/ywd1278/service/classic_tx_console.py",
        ):
            self.assertNotIn("timed_link", (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
