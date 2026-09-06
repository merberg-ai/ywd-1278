#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_CLASSIC_BBS_BLOB = "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd"
QUALIFICATION_RECORD = (
    ROOT / "docs/qualifications/0i-p2-classic-bbs-commands-host-qualified-2026-09-06.md"
)


class ClassicBBSP2QualificationContract(unittest.TestCase):
    def test_qualified_source_blob_is_exact(self) -> None:
        actual = subprocess.check_output(
            ["git", "hash-object", "src/ywd1278/node/classic_bbs.py"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(actual, QUALIFIED_CLASSIC_BBS_BLOB)

    def test_qualification_record_pins_candidate_and_ci(self) -> None:
        text = QUALIFICATION_RECORD.read_text(encoding="utf-8")
        self.assertIn("516a3e8960b542b69dd043713a20250e49db055d", text)
        self.assertIn("34008133364", text)
        self.assertIn(QUALIFIED_CLASSIC_BBS_BLOB, text)
        self.assertIn("No target-Pi or RF test is required for P2", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
