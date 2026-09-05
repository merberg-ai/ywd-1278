#!/usr/bin/env python3
"""Sealed contract for operator-provided P5e physical ID evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p5e-id-target-pi.json"


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicIDP5ePhysicalEvidenceContractTests(unittest.TestCase):
    def test_exact_physical_acceptance(self) -> None:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "target-pi-physical-qualified")
        auth = data["authorization"]
        self.assertEqual(auth["pre_rf_sha"], "58e64e74faa4389cb0f02d77ce1f4c8a73c7d2df")
        self.assertTrue(auth["authorization_consumed"])
        self.assertEqual(auth["authorized_id_commands"], 1)
        self.assertFalse(auth["automatic_retry_authorized"])
        self.assertFalse(auth["beacon_scheduler_authorized"])

        product = data["product_under_test"]
        self.assertEqual(product["frequency_hz"], 145050000)
        self.assertEqual(product["tx_power"], 200)
        self.assertFalse(product["persistent_tx_enabled_before"])
        self.assertFalse(product["persistent_beacon_enabled_before"])

        vector = data["fixed_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "ID")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["information"], "YWD-1278 ID KJ6YWD-10")
        self.assertEqual(vector["information_bytes"], 21)

        command = data["command_and_tx"]
        self.assertEqual(command["manual_id_commands"], 1)
        self.assertEqual(command["internal_tx_dispatches"], 1)
        self.assertFalse(command["beacon_scheduler_used"])
        self.assertTrue(command["no_automatic_retry_after_settle"])
        self.assertFalse(command["automatic_tx_retry"])

        external = data["independent_over_air_decode"]
        self.assertTrue(external["operator_confirmed_exact_match"])
        self.assertEqual(external["decode_count"], 1)
        self.assertEqual(external["information_length"], 21)
        self.assertTrue(external["screenshot_provided_in_conversation"])

        rx = data["post_tx_rx_recovery"]
        self.assertTrue(rx["resumed"])
        self.assertEqual(rx["frame_bytes"], 36)
        self.assertEqual(rx["source"], "KJ6YWD-5")

        cleanup = data["cleanup_and_safety"]
        self.assertFalse(cleanup["beacon_scheduler_used"])
        self.assertFalse(cleanup["persistent_tx_enabled_final"])
        self.assertFalse(cleanup["persistent_config_mutated"])
        self.assertTrue(cleanup["normal_service_restored"])
        self.assertFalse(cleanup["flash_written"])
        self.assertFalse(cleanup["option_bytes_written"])
        self.assertTrue(data["p5e_complete"])

    def test_physically_executed_harness_is_byte_exact(self) -> None:
        self.assertEqual(
            git_blob(ROOT / "tools/qualify_0f_p5e_id.py"),
            "bf3ab5aeacc6701d2b9302660ef2cedc58a85ba2",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
