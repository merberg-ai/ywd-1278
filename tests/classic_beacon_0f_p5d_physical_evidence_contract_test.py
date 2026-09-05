#!/usr/bin/env python3
"""Sealed contract for operator-provided P5d physical evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p5d-beacon-target-pi.json"


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicBeaconP5dPhysicalEvidenceContractTests(unittest.TestCase):
    def test_exact_physical_acceptance(self) -> None:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "target-pi-physical-qualified")
        self.assertEqual(data["authorization"]["pre_rf_sha"], "37feec11a87ba4ad864c61b11d75c0b0631d6a67")
        self.assertTrue(data["authorization"]["authorization_consumed"])
        self.assertEqual(data["authorization"]["authorized_beacon_events"], 1)
        self.assertFalse(data["authorization"]["automatic_retry_authorized"])

        product = data["product_under_test"]
        self.assertEqual(product["frequency_hz"], 145050000)
        self.assertEqual(product["tx_power"], 200)
        self.assertFalse(product["persistent_tx_enabled_before"])
        self.assertFalse(product["persistent_beacon_enabled_before"])

        vector = data["fixed_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "BEACON")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["information"], "YWD-1278 0F-P5D BEACON 1/1")
        self.assertEqual(vector["information_bytes"], 26)

        scheduler = data["scheduler_and_tx"]
        self.assertEqual(scheduler["scheduled_beacon_events"], 1)
        self.assertEqual(scheduler["internal_tx_dispatches"], 1)
        self.assertTrue(scheduler["beacon_off_after_first_dispatch"])
        self.assertTrue(scheduler["no_second_dispatch_after_full_interval"])
        self.assertFalse(scheduler["automatic_tx_retry"])

        external = data["independent_over_air_decode"]
        self.assertTrue(external["operator_confirmed_exact_match"])
        self.assertEqual(external["decode_count"], 1)
        self.assertEqual(external["information_length"], 26)
        self.assertTrue(external["screenshot_provided_in_conversation"])

        rx = data["post_tx_rx_recovery"]
        self.assertTrue(rx["resumed"])
        self.assertEqual(rx["frame_bytes"], 254)
        self.assertEqual(rx["source"], "KJ6YWD-5")

        cleanup = data["cleanup_and_safety"]
        self.assertFalse(cleanup["beacon_enabled_final"])
        self.assertFalse(cleanup["persistent_tx_enabled_final"])
        self.assertFalse(cleanup["persistent_config_mutated"])
        self.assertTrue(cleanup["normal_service_restored"])
        self.assertFalse(cleanup["flash_written"])
        self.assertFalse(cleanup["option_bytes_written"])

        wrapper = data["operator_shell_note"]
        self.assertEqual(wrapper["harness_exit"], "PASS")
        self.assertTrue(wrapper["post_harness_wrapper_error"])
        self.assertFalse(wrapper["affects_physical_result"])
        self.assertTrue(wrapper["putty_session_survived"])

    def test_physically_executed_harness_is_byte_exact(self) -> None:
        self.assertEqual(
            git_blob(ROOT / "tools/qualify_0f_p5d_beacon.py"),
            "ec2873ab432a9bfee1470a11c5aac29c6099d55f",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
