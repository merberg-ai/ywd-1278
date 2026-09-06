#!/usr/bin/env python3
"""Immutable evidence contract for physically qualified 0H-P10."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0h-p10-linbpq-delivery-target-pi.json"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class LinBPQDeliveryP10PhysicalEvidenceTests(unittest.TestCase):
    def test_exact_physical_acceptance(self) -> None:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(data["qualification_result"], "PASS")
        self.assertEqual(data["candidate_commit"], "da7c7975b4651e06a7a9d7aeff37ab19eafd8525")
        self.assertEqual(data["host_base_checkpoint"], "618585fd2588235296a281022cf39feb5f2ba8e9")
        self.assertEqual(data["harness_revision"], "R3")
        self.assertEqual((data["frequency_hz"], data["tx_power"]), (145050000, 200))
        self.assertEqual(
            (data["local_source"], data["remote_listener"], data["bbs_identity"]),
            ("KJ6YWD-10", "KJ6YWD-5", "KJ6YWD-1"),
        )
        self.assertEqual(data["destination_requested"], "KJ6YWD-15")
        self.assertEqual(data["linbpq_stored_recipient"], "KJ6YWD")
        self.assertEqual((data["subject"], data["body"]), ("P10 TEST", "YWD-1278 0H-P10 LINBPQ DELIVERY 1/1"))
        self.assertEqual((data["linbpq_message_number"], data["linbpq_bid"], data["linbpq_message_size"]), (464, "464_KJ6YWD", 37))
        self.assertEqual(data["rf_link_policy"], "stop-and-wait MAXFRAME=1")
        self.assertEqual((data["link_receive_paclen"], data["outbound_information_max"]), (256, 128))
        for key in (
            "sabm_ua_exchange_pass",
            "bbs_entry_submitted",
            "bpq_sid_observed_pass",
            "bbs_prompt_observed_pass",
            "live_title_prompt_pass",
            "live_body_prompt_pass",
            "message_submission_prompt_return_pass",
            "disc_ua_exchange_pass",
            "one_message_submitted",
            "normal_service_restored",
        ):
            self.assertIs(data[key], True, key)
        self.assertEqual(data["p9_dialogue_actions"], ["SP", "TITLE", "BODY", "BODY_END", "END"])
        self.assertEqual(data["link_actions_submitted"], 13)
        self.assertIs(data["persistent_tx_enabled_final"], False)
        self.assertIs(data["persistent_config_mutated"], False)
        self.assertIs(data["flash_written"], False)
        self.assertIs(data["option_bytes_written"], False)
        self.assertIn("Message: 464 Bid:  464_KJ6YWD Size: 37", data["remote_transcript_escaped"])
        self.assertTrue(data["remote_transcript_escaped"].endswith("de KJ6YWD>\\x0d"))

    def test_evidence_and_executed_harness_are_byte_exact(self) -> None:
        self.assertEqual(blob(EVIDENCE), "617d891bce3b106a1744a2418b6788e92e16659c")
        self.assertEqual(blob(ROOT / "tools/qualify_0h_p10_linbpq_delivery_r3.py"), "c4399d6be22d00b4bee5d9731cea34d38ca1b7a0")
        self.assertEqual(blob(ROOT / "tools/qualify_0h_p10_linbpq_delivery_r2.py"), "ee431784ea8cf35d745cb7f2f394522d3c152aaf")
        self.assertEqual(blob(ROOT / "tools/qualify_0h_p10_linbpq_delivery.py"), "381953517a5f7e70bb545ff806dad5d7288cbae1")
        self.assertEqual(blob(ROOT / "src/ywd1278/node/linbpq_dialogue.py"), "6c3776b7ffe92cb6216c682fc7c12081c57d12aa")


if __name__ == "__main__":
    unittest.main(verbosity=2)
