#!/usr/bin/env python3
"""Immutable evidence contract for physically executed 0G-P6."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0g-p6-connected-target-pi.json"


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ConnectedPhysicalP6EvidenceTests(unittest.TestCase):
    def test_exact_connected_acceptance(self) -> None:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(data["candidate_commit"], "3169ca5726023e35dbb163daa10ce8ea185d517c")
        self.assertEqual((data["frequency_hz"], data["tx_power"]), (145050000, 200))
        self.assertEqual((data["source"], data["remote"]), ("KJ6YWD-10", "KJ6YWD-5"))
        self.assertEqual(data["information"], "YWD-1278 0G-P6 CONNECTED TEST 1/1")
        for key in (
            "dry_run_pass", "service_eligibility_pass", "hat_detect_pass",
            "sabm_ua_exchange_pass", "i_rr_exchange_pass", "disc_ua_exchange_pass",
            "normal_service_restored",
        ):
            self.assertIs(data[key], True, key)
        self.assertEqual(data["new_information_frames"], 1)
        self.assertEqual(data["link_actions_submitted"], 3)
        self.assertEqual(data["remote_text_lines"], 0)
        remote = data["independent_remote_capture"]
        self.assertEqual(remote["system"], "KJ6YWD-5 LinBPQ")
        for key in ("sabm_seen", "i_frame_seen", "information_exact", "disc_seen"):
            self.assertIs(remote[key], True, key)
        self.assertEqual(remote["capture_times"], ["14:52:16", "14:52:19", "14:52:21"])
        self.assertIs(data["persistent_tx_enabled_final"], False)
        self.assertIs(data["persistent_config_mutated"], False)
        self.assertIs(data["flash_written"], False)
        self.assertIs(data["option_bytes_written"], False)

    def test_executed_harness_is_byte_exact(self) -> None:
        self.assertEqual(
            git_blob(ROOT / "tools/qualify_0g_p6_connected.py"),
            "5a48bb4f24aac078c01c977de7633c70c9a97aa4",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
