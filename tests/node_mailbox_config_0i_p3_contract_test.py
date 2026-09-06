#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN_P2_BBS_BLOB = "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd"
FROZEN_P1_STORE_BLOB = "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


class NodeMailboxConfigP3ContractTests(unittest.TestCase):
    def test_p1_and_p2_sources_remain_byte_exact(self) -> None:
        self.assertEqual(git_blob("src/ywd1278/node/classic_bbs.py"), FROZEN_P2_BBS_BLOB)
        self.assertEqual(git_blob("src/ywd1278/node/persistent_mailbox.py"), FROZEN_P1_STORE_BLOB)

    def test_config_layer_has_no_runtime_capability_imports(self) -> None:
        source = (ROOT / "src/ywd1278/service/node_mailbox_config.py").read_text(encoding="utf-8")
        for token in (
            "from ywd1278.modem",
            "from ywd1278.kiss",
            "from ywd1278.link",
            "from ywd1278.tx",
            "import socket",
            "import threading",
            "/dev/tty",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_p3_does_not_wire_classic_bbs_into_daemon(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertNotIn("ClassicBBSSession", daemon)
        self.assertNotIn("PersistentMailboxStore", daemon)
        self.assertNotIn("node_mailbox_config", daemon)

    def test_example_keeps_node_mailbox_and_forwarding_disabled(self) -> None:
        example = (ROOT / "config/ywd-1278.example.toml").read_text(encoding="utf-8")
        self.assertIn("[node]", example)
        self.assertIn("[mailbox]", example)
        self.assertIn('database = "/var/lib/ywd-1278/mailbox.sqlite3"', example)
        self.assertGreaterEqual(example.count("enabled = false"), 4)
        forwarding = example.split("[forwarding]", 1)[1].split("[beacon]", 1)[0]
        self.assertIn("enabled = false", forwarding)


if __name__ == "__main__":
    unittest.main(verbosity=2)
