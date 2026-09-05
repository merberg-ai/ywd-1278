#!/usr/bin/env python3
"""Architecture and preservation contract for 0G-P2."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/link/modulo8.py": "9ebaa1c07923060adbc568d1825ac6bf40a69579",
    "tests/modulo8_link_0g_p1_test.py": "7f536a95c3f137b3d7b5c383ccedb2300c538930",
    "tests/modulo8_link_0g_p1_contract_test.py": "f837f03b741d0b457bf481aa1c386593d0ab5c7b",
    "src/ywd1278/service/beacon_access_policy.py": "534a65da6010a57bdddcc1aec4913bb9493cc631",
    "src/ywd1278/daemon.py": "f5ff3c6d9feea4c020d84d13795cfcca40ef186f",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class Modulo8DataLinkP2ContractTests(unittest.TestCase):
    def test_p1_and_0f_lineage_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_p2_has_bounded_sequence_and_supervisory_vocabulary(self) -> None:
        text = (ROOT / "src/ywd1278/link/data_link.py").read_text(encoding="utf-8")
        for marker in (
            'S_CONTROL = {"RR": 0x01, "RNR": 0x05, "REJ": 0x09}',
            "not 1 <= maxframe <= 7", "not 1 <= paclen <= 256",
            'return self._reject("MAXFRAME window is full")',
            "self._vs = sequence_next(self._vs)",
            "self._vr = sequence_next(self._vr)",
            "self._va = nr", "del self._outstanding[:count]",
            'DataLinkAction("I", frame, True)',
        ):
            self.assertIn(marker, text)

    def test_p2_has_no_active_runtime_or_automatic_retry(self) -> None:
        text = (ROOT / "src/ywd1278/link/data_link.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading", "time.sleep(", "socket", "KISSMessage(",
            "reject_client_message", "ProductBeaconScheduler(", "TXModemOwner(",
            "PosixSerialTransport(", "RPi.GPIO", "subprocess", "open(",
            "def tick", "def retry",
        ):
            self.assertNotIn(forbidden, text)

    def test_existing_product_owners_do_not_import_p2(self) -> None:
        for relative in (
            "src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py",
            "src/ywd1278/service/classic_tx_console.py",
        ):
            self.assertNotIn("data_link", (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
