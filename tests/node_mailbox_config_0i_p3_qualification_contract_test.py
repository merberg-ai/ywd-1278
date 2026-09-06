#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_CONFIG_BLOB = "a56d8981888ebffd1aa22d895d53db7326e9d6bc"
RECORD = ROOT / "docs/qualifications/0i-p3-node-mailbox-config-host-qualified-2026-09-06.md"

class NodeMailboxP3QualificationContract(unittest.TestCase):
    def test_source_blob(self) -> None:
        actual = subprocess.check_output(
            ["git", "hash-object", "src/ywd1278/service/node_mailbox_config.py"],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(actual, QUALIFIED_CONFIG_BLOB)

    def test_record(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        self.assertIn("bf10534265891e99b3c0100564d81b83c7b9d66e", text)
        self.assertIn("34008269050", text)
        self.assertIn(QUALIFIED_CONFIG_BLOB, text)

if __name__ == "__main__":
    unittest.main(verbosity=2)
