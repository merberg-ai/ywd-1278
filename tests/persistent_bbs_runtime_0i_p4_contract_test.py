#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
    "src/ywd1278/node/inbound.py": "121b4505f1ceb183d840e426fc855d82736039c4",
    "src/ywd1278/link/timed_link.py": "229b93ccc9ae2745ca1aae48685ced8712f5d433",
}

class PersistentBBSRuntimeP4ContractTests(unittest.TestCase):
    def test_frozen_dependencies_are_byte_exact(self) -> None:
        for path, expected in FROZEN.items():
            with self.subTest(path=path):
                actual = subprocess.check_output(
                    ["git", "hash-object", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(actual, expected)

    def test_runtime_owns_no_product_transport_or_rf_path(self) -> None:
        source = (ROOT / "src/ywd1278/node/persistent_bbs_runtime.py").read_text(encoding="utf-8")
        for token in (
            "from ywd1278.modem",
            "from ywd1278.kiss",
            "from ywd1278.tx",
            "import socket",
            "import threading",
            "/dev/tty",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_conservative_connected_policy_is_explicit(self) -> None:
        source = (ROOT / "src/ywd1278/node/persistent_bbs_runtime.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_CONNECTED_MAXFRAME = 1", source)
        self.assertIn("DEFAULT_CONNECTED_RECEIVE_PACLEN = 256", source)
        self.assertIn("t1_seconds=35.0", source)
        self.assertIn("max_retries=2", source)
        self.assertIn('frame_type="DM"', source)

    def test_p4_is_not_yet_wired_into_daemon(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertNotIn("PersistentBBSRuntime", daemon)
        self.assertNotIn("persistent_bbs_runtime", daemon)

if __name__ == "__main__":
    unittest.main(verbosity=2)
