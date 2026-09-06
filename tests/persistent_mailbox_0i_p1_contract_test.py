#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]

FROZEN_0H_MAILBOX_BLOB = "4e8843887c1c5d242014f4301cc47a93b7b84421"
FROZEN_P11_COORDINATOR_BLOB = "ce4ee0b1b132ac6881a48f8e20b0c2c1322dac52"
FROZEN_P11_FORWARDING_CONFIG_BLOB = "f30617e6611997faf8ef2cc016b4d787012b097e"


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


class PersistentMailboxP1ContractTests(unittest.TestCase):
    def test_frozen_0h_mailbox_and_p11_forwarding_remain_byte_exact(self) -> None:
        self.assertEqual(git_blob("src/ywd1278/node/mailbox.py"), FROZEN_0H_MAILBOX_BLOB)
        self.assertEqual(
            git_blob("src/ywd1278/node/forwarding_coordinator.py"),
            FROZEN_P11_COORDINATOR_BLOB,
        )
        self.assertEqual(
            git_blob("src/ywd1278/service/forwarding_config.py"),
            FROZEN_P11_FORWARDING_CONFIG_BLOB,
        )

    def test_new_store_is_not_wired_into_daemon_or_appliance(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        appliance = (ROOT / "src/ywd1278/service/appliance.py").read_text(encoding="utf-8")
        self.assertNotIn("persistent_mailbox", daemon)
        self.assertNotIn("PersistentMailboxStore", daemon)
        self.assertNotIn("persistent_mailbox", appliance)
        self.assertNotIn("PersistentMailboxStore", appliance)

    def test_new_store_has_no_runtime_or_rf_ownership_imports(self) -> None:
        source = (ROOT / "src/ywd1278/node/persistent_mailbox.py").read_text(encoding="utf-8")
        forbidden = (
            "ywd1278.modem",
            "ywd1278.phy",
            "ywd1278.tx",
            "ywd1278.kiss",
            "ywd1278.link",
            "socket",
            "threading",
            "subprocess",
            "/dev/tty",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_p1_contract_is_dedicated_persistent_schema_not_migration_of_0h_store(self) -> None:
        source = (ROOT / "src/ywd1278/node/persistent_mailbox.py").read_text(encoding="utf-8")
        self.assertIn("BBS_MAILBOX_SCHEMA_VERSION = 1", source)
        self.assertIn("message_reads", source)
        self.assertIn("MailboxMessageType", source)
        self.assertIn("killed_at_ns", source)
        self.assertIn("bid TEXT UNIQUE", source)
        self.assertIn("Address(value.callsign, 0).callsign", source)
        self.assertNotIn("from ywd1278.node.mailbox import", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
