#!/usr/bin/env python3
"""Physical evidence contract for 0F-P7 permanent product converse qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p7-product-converse-target-pi.json"
DOC = ROOT / "docs/qualifications/0f-p7-product-converse-physical-qualified-2026-09-06.md"
P4_ACCEPTANCE = ROOT / "firmware/qualification/0f-p4-classic-tx-acceptance.json"
P4_EVIDENCE = ROOT / "firmware/qualification/0f-p4-classic-tx-target-pi.json"
P4_CONTRACT = ROOT / "tests/classic_tx_0f_p4_physical_evidence_contract_test.py"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductConverse0FP7PhysicalEvidenceTests(unittest.TestCase):
    def test_exact_physical_result(self) -> None:
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(d["schema"], 1)
        self.assertEqual(d["stage"], "0F-P7")
        self.assertEqual(d["status"], "target-pi-physical-product-converse-qualified")

        tested = d["tested_source"]
        self.assertEqual(tested["commit"], "4971a0d332cd154ea0d5fdfc8e23949496549f94")
        self.assertEqual(tested["tree"], "d7452afdf855dc34c0705dcad15b48af6dff9f79")

        baseline = d["installed_recovery_baseline"]
        self.assertEqual(baseline["commit"], "b10bae526c9f21ee36d6531dfbb44feb0816fd24")
        self.assertEqual(
            baseline["persistent_config_sha256"],
            "2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76",
        )
        self.assertFalse(baseline["persistent_tx_enabled"])
        self.assertFalse(baseline["persistent_beacon_enabled"])

        rf = d["rf_profile"]
        self.assertEqual(rf["frequency_hz"], 145050000)
        self.assertEqual(rf["tx_power"], 200)
        self.assertEqual(rf["source"], "KJ6YWD-10")

        vector = d["qualified_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "YWD127")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["control"], "UI")
        self.assertEqual(vector["pid"], "F0")
        self.assertEqual(vector["information"], "YWD-1278 PRODUCT CONVERSE 1/1")
        self.assertEqual(
            vector["expected_external_decode"],
            "KJ6YWD-10>YWD127:YWD-1278 PRODUCT CONVERSE 1/1",
        )
        self.assertEqual(vector["independent_exact_decode_count"], 1)
        self.assertTrue(vector["independent_decoder_screenshot_observed"])
        self.assertFalse(vector["raw_screenshot_archived_in_repository"])

        q = d["qualified_behavior"]
        self.assertTrue(q["product_telnet_converse_entered"])
        self.assertTrue(q["command_prompt_suppressed_while_conversing"])
        self.assertEqual(q["classic_converse_tx_lines"], 1)
        self.assertEqual(q["tx_origin"], "PRODUCT_TELNET_CONVERSE")
        self.assertEqual(q["kiss_tx_messages"], 0)
        self.assertEqual(q["tx_dispatches"], 1)
        self.assertEqual(q["tx_queue_accepted"], 1)
        self.assertEqual(q["tx_queue_dispatched"], 1)
        self.assertEqual(q["subscriber_drops"], 0)
        self.assertTrue(q["no_second_internal_dispatch_after_hold"])
        self.assertFalse(q["automatic_tx_retry"])
        self.assertTrue(q["same_session_live_rx"])
        self.assertEqual(q["same_session_live_rx_line"], "RX KJ6YWD>JIM:yooooooooo hellooooooo")
        self.assertTrue(q["printable_cmd_escape"])
        self.assertTrue(q["command_prompt_restored"])

        safety = d["final_safety_state"]
        self.assertFalse(safety["persistent_tx_enabled"])
        self.assertFalse(safety["persistent_config_mutated"])
        self.assertFalse(safety["installed_source_mutated"])
        self.assertTrue(safety["normal_service_restored"])
        self.assertFalse(safety["firmware_written"])
        self.assertFalse(safety["option_bytes_written"])

    def test_historical_0f_p4_evidence_remains_frozen(self) -> None:
        self.assertEqual(blob(P4_ACCEPTANCE), "3c9b172cb5c0d4d49ecc383cecfc8e53b4dfa4cb")
        self.assertEqual(blob(P4_EVIDENCE), "89173148c27811b44ee25064f046d62bb83c8440")
        self.assertEqual(blob(P4_CONTRACT), "f3a534fdfeac8398b8b614c2f38222c72e2faf40")

    def test_scope_is_explicit_and_doc_pins_tested_source(self) -> None:
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        not_qualified = set(d["scope_boundary"]["not_qualified_by_this_slice"])
        self.assertIn("persistent TX enablement", not_qualified)
        self.assertIn("multi-line sustained converse RF operation", not_qualified)
        self.assertIn("physical Ctrl-C escape", not_qualified)
        self.assertIn("VIA/digipeater product-session RF path", not_qualified)
        self.assertIn("BEACON/BTEXT/ID RF behavior", not_qualified)
        self.assertIn("connected-mode CONNECT behavior", not_qualified)

        text = DOC.read_text(encoding="utf-8")
        self.assertIn("PHYSICALLY QUALIFIED", text)
        self.assertIn("4971a0d332cd154ea0d5fdfc8e23949496549f94", text)
        self.assertIn("b10bae526c9f21ee36d6531dfbb44feb0816fd24", text)
        self.assertIn("NORMAL_SERVICE_RESTORED=YES", text)

        print("YWD1278_0F_P7_PRODUCT_CONVERSE_PHYSICAL_EVIDENCE=PASS")
        print("PERMANENT_PRODUCT_CONVERSE_RF=QUALIFIED")
        print("CLASSIC_CONVERSE_TX_LINES=1")
        print("SAME_SESSION_LIVE_RX=PASS")
        print("PRINTABLE_CMD_ESCAPE=PASS")
        print("AUTOMATIC_TX_RETRY=NO")
        print("PERSISTENT_TX_ENABLED=NO")
        print("NORMAL_SERVICE_RESTORED=YES")
        print("HISTORICAL_0F_P4_EVIDENCE=FROZEN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
