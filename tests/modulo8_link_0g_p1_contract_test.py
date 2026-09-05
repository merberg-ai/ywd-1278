#!/usr/bin/env python3
"""Architecture and preservation contract for 0G-P1."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/service/beacon_access_policy.py": "534a65da6010a57bdddcc1aec4913bb9493cc631",
    "src/ywd1278/daemon.py": "f5ff3c6d9feea4c020d84d13795cfcca40ef186f",
    "tests/product_beacon_access_0f_p6_contract_test.py": "aae8ba6ef519595e1deee77c00de624e44da863e",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
    "tests/classic_id_0f_p5e_physical_evidence_contract_test.py": "2513bde062ffb272055fa0a5aec21ab5b2dba7aa",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class Modulo8LinkP1ContractTests(unittest.TestCase):
    def test_0f_and_physical_lineage_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_p1_states_and_control_vocabulary_are_explicit(self) -> None:
        text = (ROOT / "src/ywd1278/link/modulo8.py").read_text(encoding="utf-8")
        for marker in (
            'DISCONNECTED = "DISCONNECTED"',
            'AWAITING_CONNECTION = "AWAITING_CONNECTION"',
            'CONNECTED = "CONNECTED"',
            'AWAITING_RELEASE = "AWAITING_RELEASE"',
            '"DM": 0x0F', '"SABM": 0x2F', '"DISC": 0x43', '"UA": 0x63',
            'return (value + 1) & 0x07', 'return (end - start) & 0x07',
        ):
            self.assertIn(marker, text)

    def test_p1_has_no_active_runtime_or_data_transfer_capability(self) -> None:
        text = (ROOT / "src/ywd1278/link/modulo8.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading", "time.sleep(", "socket", "KISSMessage(",
            "reject_client_message", "ProductBeaconScheduler(", "TXModemOwner(",
            "PosixSerialTransport(", "RPi.GPIO", "subprocess", "open(",
        ):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("def send_information", text)
        self.assertNotIn("def tick", text)
        self.assertNotIn("def retry", text)

    def test_no_existing_product_owner_imports_link_state(self) -> None:
        for relative in (
            "src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py",
            "src/ywd1278/service/classic_tx_console.py",
        ):
            self.assertNotIn("ywd1278.link", (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
