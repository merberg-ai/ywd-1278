#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/node/commands.py": "85c02074e403f208af9fc9bd56e3f70f29af4c07",
    "tests/node_commands_0h_p1_test.py": "883c19f510607674ee321e7fb4f857b4bc566ba5",
    "tests/node_commands_0h_p1_contract_test.py": "6c6df37185245a627e6f557bb022e636dd88b6c7",
    "firmware/qualification/0g-p6-connected-target-pi.json": "5050477cf15fbc8638adb3d793ebc9fc9ad63cbe",
}

def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

class MailboxStorageP2ContractTests(unittest.TestCase):
    def test_p1_and_connected_evidence_are_frozen(self) -> None:
        for path, expected in FROZEN.items(): self.assertEqual(blob(ROOT / path), expected)
    def test_storage_is_bounded_versioned_and_owner_scoped(self) -> None:
        text = (ROOT / "src/ywd1278/node/mailbox.py").read_text(encoding="utf-8")
        for marker in ("MAILBOX_SCHEMA_VERSION = 1", "MAX_SUBJECT_BYTES = 64", "MAX_BODY_BYTES = 4096", "MAX_MESSAGES_PER_RECIPIENT = 100", "MAX_MESSAGES_TOTAL = 1000", "BEGIN IMMEDIATE", "WHERE id = ? AND recipient = ?", "mailbox file identity changed"):
            self.assertIn(marker, text)
    def test_no_runtime_forwarding_deletion_or_hardware(self) -> None:
        text = (ROOT / "src/ywd1278/node/mailbox.py").read_text(encoding="utf-8")
        for forbidden in ("DELETE FROM", "UPDATE messages", "socket", "threading", "subprocess", "TXModemOwner", "session_manager", "forward_message"):
            self.assertNotIn(forbidden, text)
        for path in ("src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py", "src/ywd1278/node/commands.py"):
            self.assertNotIn("node.mailbox", (ROOT / path).read_text(encoding="utf-8"))

if __name__ == "__main__": unittest.main(verbosity=2)
