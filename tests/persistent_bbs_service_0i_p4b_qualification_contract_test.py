#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_SERVICE_BLOB = "b816e786de1ca3acaeb1201857bf36db2d008dcf"
RECORD = ROOT / "docs/qualifications/0i-p4b-persistent-bbs-product-service-host-qualified-2026-09-06.md"


class PersistentBBSServiceP4bQualificationContract(unittest.TestCase):
    def test_source_blob(self) -> None:
        actual = subprocess.check_output(
            ["git", "hash-object", "src/ywd1278/service/persistent_bbs_service.py"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(actual, QUALIFIED_SERVICE_BLOB)

    def test_record(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        self.assertIn("0757a11ffb25f6df11d7c7aa56e6238ed8129bb9", text)
        self.assertIn("34008681299", text)
        self.assertIn(QUALIFIED_SERVICE_BLOB, text)
        self.assertIn("No target-Pi or RF test is required for P4b", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
