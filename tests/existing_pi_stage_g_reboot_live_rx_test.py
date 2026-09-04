#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("stage_g_reboot_live_rx", TOOLS / "qualify_stage_g_reboot_live_rx.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class RebootLiveRXTests(unittest.TestCase):
    def test_parse_mheard_entry(self) -> None:
        text = "MHEARD 2\r\nKJ6YWD COUNT=4 LAST_NS=123456 DEST=APRS VIA=DIRECT\r\ncmd:"
        self.assertEqual(MOD.parse_mheard_entry(text, "kj6ywd"), (4, 123456))

    def test_parse_missing(self) -> None:
        self.assertIsNone(MOD.parse_mheard_entry("MHEARD 0\r\ncmd:", "KJ6YWD"))

    def test_advanced_new_entry(self) -> None:
        self.assertTrue(MOD.advanced(None, (1, 10)))

    def test_advanced_count(self) -> None:
        self.assertTrue(MOD.advanced((2, 10), (3, 10)))

    def test_advanced_last_ns(self) -> None:
        self.assertTrue(MOD.advanced((2, 10), (2, 11)))

    def test_not_advanced_stale(self) -> None:
        self.assertFalse(MOD.advanced((2, 10), (2, 10)))
        self.assertFalse(MOD.advanced((2, 10), None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
