#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN_P1_STORE_BLOB = "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc"
FROZEN_0H_MAILBOX_BLOB = "4e8843887c1c5d242014f4301cc47a93b7b84421"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


class ClassicBBSP2ContractTests(unittest.TestCase):
    def test_p1_store_and_0h_prototype_remain_byte_exact(self) -> None:
        self.assertEqual(
            git_blob("src/ywd1278/node/persistent_mailbox.py"), FROZEN_P1_STORE_BLOB
        )
        self.assertEqual(git_blob("src/ywd1278/node/mailbox.py"), FROZEN_0H_MAILBOX_BLOB)

    def test_command_personality_is_not_runtime_wired(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        appliance = (ROOT / "src/ywd1278/service/appliance.py").read_text(encoding="utf-8")
        self.assertNotIn("classic_bbs", daemon)
        self.assertNotIn("ClassicBBSSession", daemon)
        self.assertNotIn("classic_bbs", appliance)
        self.assertNotIn("ClassicBBSSession", appliance)

    def test_command_source_has_no_link_modem_or_rf_ownership(self) -> None:
        source = (ROOT / "src/ywd1278/node/classic_bbs.py").read_text(encoding="utf-8")
        forbidden_imports = (
            "from ywd1278.modem",
            "import ywd1278.modem",
            "from ywd1278.phy",
            "import ywd1278.phy",
            "from ywd1278.tx",
            "import ywd1278.tx",
            "from ywd1278.kiss",
            "import ywd1278.kiss",
            "from ywd1278.link",
            "import ywd1278.link",
            "import socket",
            "from socket",
            "import threading",
            "from threading",
            "/dev/tty",
        )
        for token in forbidden_imports:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_classic_vocabulary_is_explicit(self) -> None:
        source = (ROOT / "src/ywd1278/node/classic_bbs.py").read_text(encoding="utf-8")
        for token in (
            '"H", "HELP", "?"',
            'command in {"L", "LIST"}',
            'command == "LN"',
            'command == "LR"',
            'command == "LM"',
            '"R", "READ"',
            '"K", "KILL"',
            'command == "SP"',
            'command == "SB"',
            '"B", "BYE"',
            'marker == "/ABORT"',
            'marker == "/EX"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
