#!/usr/bin/env python3
"""Architecture/preservation contract for host-only 0F-P5a."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
P5A = ROOT / "src/ywd1278/console/classic_beacon.py"

FROZEN = {
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicBeaconP5aContractTests(unittest.TestCase):
    def test_frozen_p4_and_lower_boundaries_are_byte_identical(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_p5a_has_no_thread_transport_or_admission_owner(self) -> None:
        tree = ast.parse(P5A.read_text(encoding="utf-8"), filename=str(P5A))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        for forbidden in (
            "threading",
            "asyncio",
            "socket",
            "serial",
            "ywd1278.kiss",
            "ywd1278.modem",
            "ywd1278.phy",
            "ywd1278.service",
        ):
            self.assertFalse(
                any(name == forbidden or name.startswith(forbidden + ".") for name in imports),
                forbidden,
            )
        text = P5A.read_text(encoding="utf-8")
        for forbidden in ("Thread(", "Timer(", "sleep(", "tx_submitter(", "reject_client_message"):
            self.assertNotIn(forbidden, text)

    def test_scheduler_is_explicitly_polled_and_fcs_free(self) -> None:
        text = P5A.read_text(encoding="utf-8")
        self.assertIn("def take_due_beacon", text)
        self.assertIn("include_fcs=False", text)
        self.assertIn("observed + self._interval_seconds", text)
        self.assertIn("if not self.tx_snapshot.tx_enabled", text)
        self.assertIn("ID TX DEFERRED; OWNER=0F-P5e", text)

    def test_no_p5a_product_or_physical_artifact_exists(self) -> None:
        self.assertFalse((ROOT / "src/ywd1278/service/classic_beacon.py").exists())
        self.assertFalse((ROOT / "scripts/qualify-0f-p5-beacon-rf.sh").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
