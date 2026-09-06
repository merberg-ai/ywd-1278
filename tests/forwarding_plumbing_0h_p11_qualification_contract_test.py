#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

class P11QualificationContractTests(unittest.TestCase):
    def test_p11_core_is_byte_exact(self) -> None:
        self.assertEqual(blob(ROOT / "src/ywd1278/service/forwarding_config.py"), "f30617e6611997faf8ef2cc016b4d787012b097e")
        self.assertEqual(blob(ROOT / "src/ywd1278/node/forwarding_coordinator.py"), "ce4ee0b1b132ac6881a48f8e20b0c2c1322dac52")
        self.assertEqual(blob(ROOT / "tests/forwarding_plumbing_0h_p11_test.py"), "0afaec3da29fd35273f40d455de5f3b6d9a43cf0")

    def test_frozen_p8_p9_p10_lineage_remains_exact(self) -> None:
        self.assertEqual(blob(ROOT / "src/ywd1278/node/forwarding_integration.py"), "263b5583d473a5673e6dfa60978804055197f676")
        self.assertEqual(blob(ROOT / "src/ywd1278/node/linbpq_dialogue.py"), "6c3776b7ffe92cb6216c682fc7c12081c57d12aa")
        self.assertEqual(blob(ROOT / "tools/qualify_0h_p10_linbpq_delivery_r3.py"), "c4399d6be22d00b4bee5d9731cea34d38ca1b7a0")
        self.assertEqual(blob(ROOT / "firmware/qualification/0h-p10-linbpq-delivery-target-pi.json"), "617d891bce3b106a1744a2418b6788e92e16659c")

if __name__ == "__main__":
    unittest.main(verbosity=2)
