#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_PERSISTENT_MAILBOX_BLOB = "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc"
QUALIFICATION_RECORD = (
    ROOT / "docs/qualifications/0i-p1-persistent-mailbox-core-host-qualified-2026-09-06.md"
)


class PersistentMailboxP1QualificationContract(unittest.TestCase):
    def test_qualified_source_blob_is_exact(self) -> None:
        actual = subprocess.check_output(
            ["git", "hash-object", "src/ywd1278/node/persistent_mailbox.py"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(actual, QUALIFIED_PERSISTENT_MAILBOX_BLOB)

    def test_qualification_record_pins_candidate_and_ci(self) -> None:
        text = QUALIFICATION_RECORD.read_text(encoding="utf-8")
        self.assertIn("ce5da5434b6af558aaece291159bd7d8aaa08c00", text)
        self.assertIn("34007888098", text)
        self.assertIn(QUALIFIED_PERSISTENT_MAILBOX_BLOB, text)
        self.assertIn("No target-Pi or RF test is required for P1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
