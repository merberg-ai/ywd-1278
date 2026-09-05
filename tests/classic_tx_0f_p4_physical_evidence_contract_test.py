#!/usr/bin/env python3
"""Contract for the completed 0F-P4 target-Pi classic-console TX qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p4-classic-tx-target-pi.json"
PRE_RF = ROOT / "firmware/qualification/0f-p4-classic-tx-pre-rf.json"
HARNESS = ROOT / "tools/qualify_0f_p4_classic_tx.py"

EXPECTED_EVIDENCE_BLOB = "89173148c27811b44ee25064f046d62bb83c8440"
EXPECTED_PRE_RF_BLOB = "83a7711965d1e7d27ef9c5b67d12aeb257f68c5f"
EXPECTED_HARNESS_BLOB = "8ed7ea78b332539e8db48288bc96dfc14c31f23d"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicTX0FP4PhysicalEvidenceTests(unittest.TestCase):
    def test_exact_physical_evidence(self) -> None:
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        pre = json.loads(PRE_RF.read_text(encoding="utf-8"))

        self.assertEqual(d["schema"], 1)
        self.assertEqual(d["stage"], "0F-P4")
        self.assertEqual(d["status"], "target-pi-physical-tx-qualified")
        self.assertTrue(d["p4_complete"])

        auth = d["authorization"]
        self.assertEqual(auth["pre_rf_sha"], "837959a19a51e1a7e97d5fed1ce249c4b414a063")
        self.assertEqual(auth["frozen_0f_capability_base"], "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3")
        self.assertEqual(auth["authorization_token"], "0F-P4-TX-145050-ONE")
        self.assertTrue(auth["authorization_consumed"])
        self.assertEqual(auth["authorized_tx_frames"], 1)
        self.assertFalse(auth["persistent_tx_authorized"])
        self.assertFalse(auth["automatic_tx_authorized"])
        self.assertFalse(auth["beacon_tx_authorized"])
        self.assertFalse(auth["connected_mode_tx_authorized"])
        self.assertFalse(auth["firmware_write_authorized"])

        put = d["product_under_test"]
        self.assertEqual(put["installed_appliance_commit"], "2f5299e65add072fea6ee55a54dc421faf00c276")
        self.assertEqual(put["frequency_hz"], 145050000)
        self.assertEqual(put["tx_power"], 200)
        self.assertEqual(put["firmware_sha256"], "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616")
        self.assertEqual(put["persistent_config_sha256"], "2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76")
        self.assertFalse(put["persistent_tx_enabled_before"])
        self.assertFalse(put["persistent_beacon_enabled_before"])
        self.assertEqual(put["service_eligibility_check"], "PASS")
        self.assertEqual(put["hat_detect"], "PASS")

        vector = d["fixed_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "YWD127")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["control"], "UI")
        self.assertEqual(vector["pid"], "F0")
        self.assertEqual(vector["information"], "YWD-1278 0F-P4 CLASSIC TX 1/1")
        self.assertEqual(vector["information_bytes"], 29)
        self.assertEqual(vector["tx_origin"], "classic Telnet UNPROTO/CONVERSE session")

        classic = d["classic_console_path"]
        self.assertTrue(classic["unproto_direct"])
        self.assertTrue(classic["converse_entered"])
        self.assertEqual(classic["converse_tx_lines"], 1)
        self.assertTrue(classic["command_mode_restored_immediately"])
        self.assertEqual(classic["kiss_tx_messages"], 0)
        self.assertEqual(classic["backend_data_admitted"], 1)

        tx = d["product_tx_accounting"]
        self.assertEqual(tx["tx_dispatches"], 1)
        self.assertEqual(tx["tx_queue_accepted"], 1)
        self.assertEqual(tx["tx_queue_dispatched"], 1)
        self.assertFalse(tx["automatic_tx_retry"])
        self.assertTrue(tx["no_second_internal_dispatch_after_hold"])

        ext = d["independent_over_air_decode"]
        self.assertTrue(ext["operator_confirmed_exact_match"])
        self.assertEqual(ext["decode_count"], 1)
        self.assertTrue(ext["screenshot_provided_in_conversation"])
        self.assertEqual(ext["screenshot_control"], "UI")
        self.assertEqual(ext["screenshot_pid"], "F0(Text)")
        self.assertEqual(ext["screenshot_information_length"], 29)
        self.assertEqual(ext["screenshot_information"], "YWD-1278 0F-P4 CLASSIC TX 1/1")
        self.assertFalse(ext["raw_screenshot_archived_in_repository"])

        rx = d["post_tx_rx_recovery"]
        self.assertTrue(rx["resumed"])
        self.assertEqual(rx["frame_bytes"], 15)
        self.assertEqual(rx["source"], "KJ6YWD-5")
        self.assertTrue(rx["source_differs_from_tx_source"])
        self.assertEqual(rx["final_tx_dispatches"], 1)
        self.assertEqual(rx["tx_queue_depth_final"], 0)
        self.assertEqual(rx["subscriber_drops_final"], 0)
        self.assertEqual(rx["tx_access_timeouts_final"], 0)
        self.assertEqual(rx["tx_downstream_failures_final"], 0)

        cleanup = d["cleanup_and_safety"]
        self.assertFalse(cleanup["persistent_tx_enabled_final"])
        self.assertFalse(cleanup["persistent_config_mutated"])
        self.assertTrue(cleanup["normal_service_restored"])
        self.assertFalse(cleanup["beacon_tx"])
        self.assertFalse(cleanup["connected_mode_tx"])
        self.assertFalse(cleanup["automatic_tx_retry"])
        self.assertFalse(cleanup["kiss_data_sent_by_harness"])
        self.assertFalse(cleanup["flash_written"])
        self.assertFalse(cleanup["option_bytes_written"])

        self.assertEqual(pre["status"], "pre-rf-staged-authorized")
        self.assertFalse(pre["operator_authorization"]["authorization_consumed"])
        self.assertFalse(pre["physical"]["rf_transmitted"])

        self.assertEqual(blob(EVIDENCE), EXPECTED_EVIDENCE_BLOB)
        self.assertEqual(blob(PRE_RF), EXPECTED_PRE_RF_BLOB)
        self.assertEqual(blob(HARNESS), EXPECTED_HARNESS_BLOB)

        print("YWD1278_0F_P4_PHYSICAL_EVIDENCE=PASS")
        print("CLASSIC_CONVERSE_TX_LINES=1")
        print("KISS_TX_MESSAGES=0")
        print("INTERNAL_TX_DISPATCHES=1")
        print("INDEPENDENT_EXACT_DECODE=YES")
        print("POST_TX_RX_SOURCE=KJ6YWD-5")
        print("PERSISTENT_TX_ENABLED_FINAL=NO")
        print("NORMAL_SERVICE_RESTORED=YES")
        print("BEACON_TX=NO")
        print("CONNECTED_MODE_TX=NO")
        print("FLASH_WRITTEN=NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
