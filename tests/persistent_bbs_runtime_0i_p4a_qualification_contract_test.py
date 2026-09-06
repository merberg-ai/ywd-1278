#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_RUNTIME_BLOB = "0c40aaf283142b71d16c9f30a1687865a98b197f"
RECORD = ROOT / "docs/qualifications/0i-p4a-persistent-bbs-runtime-host-qualified-2026-09-06.md"


class PersistentBBSRuntimeP4aQualificationContract(unittest.TestCase):
    def test_source_blob(self) -> None:
        actual = subprocess.check_output(
            ["git", "hash-object", "src/ywd1278/node/persistent_bbs_runtime.py"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(actual, QUALIFIED_RUNTIME_BLOB)

    def test_record(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        self.assertIn("5ac31ddb7e952004aa925938ffd114d48a151aaa", text)
        self.assertIn("34008488519", text)
        self.assertIn(QUALIFIED_RUNTIME_BLOB, text)
        self.assertIn("No target-Pi or RF test is required for P4a", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
