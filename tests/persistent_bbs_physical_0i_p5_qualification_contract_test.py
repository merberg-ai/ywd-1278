#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0i-p5-persistent-bbs-target-pi.json"
DOC = ROOT / "docs/qualifications/0i-p5-persistent-bbs-physical-qualified-2026-09-07.md"
CONTROL = ROOT / "installer/persistent-bbs-physical-control.sh"

TESTED_COMMIT = "9c02f01515a0ae3a933c4471409673c7c67425c9"
TESTED_TREE = "f6893210da62cdee00559085d850678f599b5e28"
HOST_COMMIT = "dd2f96f27050bf24c57e24a9b2b3a2ba86688b27"

FROZEN_P4C2 = {
    "src/ywd1278/daemon.py": "85471ccac9e26079c0265753054d54eb1753e191",
    "src/ywd1278/service/product_mailbox_console.py": "93c9a66be6b5d01d6bacfb70b2eef7b1189a9b6c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/persistent_bbs_service.py": "b816e786de1ca3acaeb1201857bf36db2d008dcf",
    "src/ywd1278/node/persistent_bbs_runtime.py": "0c40aaf283142b71d16c9f30a1687865a98b197f",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
}


class PersistentBBSPhysicalP5QualificationContract(unittest.TestCase):
    def load_evidence(self) -> dict:
        return json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_evidence_pins_exact_physical_source_and_host_base(self) -> None:
        evidence = self.load_evidence()
        self.assertEqual(evidence["schema"], 1)
        self.assertEqual(evidence["stage"], "0I-P5")
        self.assertEqual(evidence["status"], "target-pi-persistent-bbs-physically-qualified")
        self.assertEqual(evidence["qualified_on"], "2026-09-07")
        self.assertEqual(evidence["tested_source"]["commit"], TESTED_COMMIT)
        self.assertEqual(evidence["tested_source"]["tree"], TESTED_TREE)
        self.assertEqual(evidence["host_qualified_base"]["commit"], HOST_COMMIT)

    def test_evidence_records_exact_rf_and_hardware_profile(self) -> None:
        evidence = self.load_evidence()
        self.assertEqual(evidence["rf_profile"]["frequency_hz"], 145_050_000)
        self.assertEqual(evidence["rf_profile"]["tx_power"], 200)
        self.assertEqual(evidence["rf_profile"]["bbs_station"], "KJ6YWD-10")
        self.assertEqual(evidence["rf_profile"]["direct_peer"], "KJ6YWD")
        self.assertEqual(evidence["rf_profile"]["connected_mode_digipeater_path"], [])
        self.assertTrue(evidence["hardware"]["runtime_identity_verified"])
        self.assertEqual(
            evidence["hardware"]["target_id"],
            "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021",
        )
        self.assertIn("AX25R4", evidence["hardware"]["firmware_identity"])
        self.assertFalse(evidence["hardware"]["firmware_write_during_p5"])
        self.assertFalse(evidence["hardware"]["option_byte_write_during_p5"])

    def test_evidence_records_real_bbs_and_shared_store_behavior(self) -> None:
        evidence = self.load_evidence()
        bbs = evidence["connected_bbs"]
        self.assertTrue(bbs["direct_connection_passed"])
        self.assertEqual(bbs["bulletin_saved"]["subject"], "HELLO WORLD!")
        self.assertEqual(bbs["personal_message_saved"]["subject"], "IT WORKS!")
        self.assertTrue(bbs["list_passed"])
        self.assertTrue(bbs["read_message_1_passed"])
        self.assertTrue(bbs["read_message_2_passed"])
        self.assertTrue(bbs["info_reported_forwarding_disabled"])
        self.assertTrue(bbs["bye_passed"])
        self.assertTrue(bbs["orderly_disconnect_observed"])

        local = evidence["local_mbox_shared_store"]
        self.assertEqual(local["visible_count"], 2)
        self.assertEqual(local["message_1_subject"], "HELLO WORLD!")
        self.assertEqual(local["message_2_subject"], "IT WORKS!")
        self.assertTrue(local["same_rf_created_messages_visible"])
        self.assertTrue(local["command_return_passed"])

    def test_evidence_records_rx_safe_cleanup_and_helper_repair(self) -> None:
        evidence = self.load_evidence()
        cleanup = evidence["cleanup"]
        self.assertTrue(cleanup["initial_helper_attempt_encountered_non_executable_product_tx_control"])
        self.assertTrue(cleanup["service_was_inactive_during_interruption"])
        self.assertTrue(cleanup["tx_was_explicitly_revoked_with_bash_product_tx_control"])
        self.assertTrue(cleanup["cleanup_then_completed_successfully"])
        self.assertFalse(cleanup["final_tx_enabled"])
        self.assertFalse(cleanup["final_node_enabled"])
        self.assertFalse(cleanup["final_mailbox_enabled"])
        self.assertTrue(cleanup["final_service_active"])
        self.assertTrue(cleanup["final_service_enabled"])
        self.assertFalse(cleanup["final_stage_state_present"])
        self.assertTrue(cleanup["mailbox_database_preserved"])

        repair = evidence["post_test_staging_helper_fix"]
        self.assertFalse(repair["runtime_behavior_changed"])
        self.assertEqual(repair["ci_run"], 34129834195)
        self.assertEqual(repair["ci_conclusion"], "success")
        lines = [line.strip() for line in CONTROL.read_text(encoding="utf-8").splitlines()]
        self.assertIn(
            'bash "$TX_CONTROL" disable --expected-installed-commit "$installed_commit"',
            lines,
        )

    def test_p4c2_runtime_blobs_remain_exactly_frozen(self) -> None:
        for path, expected in FROZEN_P4C2.items():
            with self.subTest(path=path):
                actual = subprocess.check_output(
                    ["git", "hash-object", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(actual, expected)

    def test_qualification_document_contains_closure_markers(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for required in (
            "Status: **PHYSICALLY QUALIFIED**",
            TESTED_COMMIT,
            TESTED_TREE,
            "145.050 MHz",
            "KJ6YWD-10",
            "HELLO WORLD!",
            "IT WORKS!",
            "shared persistent mailbox store",
            "CONFIG_TX_ENABLED=FALSE",
            "CONFIG_NODE_ENABLED=FALSE",
            "CONFIG_MAILBOX_ENABLED=FALSE",
            "P4C2_STAGE_STATE=ABSENT",
            "0I-P5 persistent BBS physical qualification: PASS",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
