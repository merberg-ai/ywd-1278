#!/usr/bin/env python3
"""Final sealed acceptance contract for 0F-P4 physical qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "firmware/qualification/0f-p4-classic-tx-acceptance.json"
EVIDENCE = ROOT / "firmware/qualification/0f-p4-classic-tx-target-pi.json"
PHYSICAL_CONTRACT = ROOT / "tests/classic_tx_0f_p4_physical_evidence_contract_test.py"

EXPECTED_ACCEPTANCE_BLOB = "3c9b172cb5c0d4d49ecc383cecfc8e53b4dfa4cb"
EXPECTED_EVIDENCE_BLOB = "89173148c27811b44ee25064f046d62bb83c8440"
EXPECTED_PHYSICAL_CONTRACT_BLOB = "f3a534fdfeac8398b8b614c2f38222c72e2faf40"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicTX0FP4FinalAcceptanceTests(unittest.TestCase):
    def test_final_acceptance_is_exact(self) -> None:
        a = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))

        self.assertEqual(a["schema"], 1)
        self.assertEqual(a["stage"], "0F-P4")
        self.assertEqual(a["status"], "physically-qualified")
        self.assertTrue(a["p4_complete"])
        self.assertEqual(a["base"]["host_sha"], "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3")
        self.assertEqual(a["base"]["pre_rf_sha"], "837959a19a51e1a7e97d5fed1ce249c4b414a063")

        pe = a["physical_evidence"]
        self.assertEqual(pe["blob"], EXPECTED_EVIDENCE_BLOB)
        self.assertEqual(pe["contract_blob"], EXPECTED_PHYSICAL_CONTRACT_BLOB)
        self.assertTrue(pe["independent_decoder_screenshot_observed"])
        self.assertFalse(pe["raw_screenshot_archived_in_repository"])

        ci = a["physical_ci"]
        self.assertEqual(ci["head"], "8eac85aaefae2ea1abbc9bf15e44f0d3edbc69cd")
        self.assertEqual(ci["run_id"], 33940024710)
        self.assertEqual(ci["conclusion"], "success")
        for key in (
            "physical_evidence_contract_passed",
            "pre_rf_evidence_preserved",
            "sealed_0f_p1_p2_p3_preserved",
            "stage_i_physical_evidence_preserved",
            "final_appliance_seal_preserved",
            "frozen_classic_console_preserved",
            "frozen_product_tx_graph_preserved",
            "sustained_packet_lineage_preserved",
        ):
            self.assertTrue(ci[key], key)

        vector = a["qualified_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "YWD127")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["control"], "UI")
        self.assertEqual(vector["pid"], "F0")
        self.assertEqual(vector["information"], "YWD-1278 0F-P4 CLASSIC TX 1/1")
        self.assertEqual(vector["information_bytes"], 29)
        self.assertEqual(vector["frequency_hz"], 145050000)
        self.assertEqual(vector["tx_power"], 200)

        q = a["qualified_behavior"]
        self.assertTrue(q["classic_unproto_direct"])
        self.assertTrue(q["classic_converse_entered"])
        self.assertEqual(q["classic_converse_tx_lines"], 1)
        self.assertTrue(q["classic_command_mode_restored"])
        self.assertTrue(q["classic_console_tx_origin"])
        self.assertEqual(q["kiss_tx_messages"], 0)
        self.assertEqual(q["internal_tx_dispatches"], 1)
        self.assertFalse(q["automatic_tx_retry"])
        self.assertEqual(q["independent_exact_over_air_decode_count"], 1)
        self.assertTrue(q["post_tx_rx_resumed"])
        self.assertEqual(q["post_tx_rx_source"], "KJ6YWD-5")
        self.assertEqual(q["post_tx_rx_frame_bytes"], 15)
        self.assertEqual(q["tx_queue_depth_final"], 0)
        self.assertEqual(q["subscriber_drops_final"], 0)
        self.assertEqual(q["tx_access_timeouts_final"], 0)
        self.assertEqual(q["tx_downstream_failures_final"], 0)

        safety = a["final_safety_state"]
        self.assertTrue(safety["authorization_consumed"])
        self.assertFalse(safety["persistent_tx_enabled"])
        self.assertFalse(safety["persistent_config_mutated"])
        self.assertTrue(safety["normal_service_restored"])
        self.assertFalse(safety["beacon_tx_exercised"])
        self.assertFalse(safety["connected_mode_tx_exercised"])
        self.assertFalse(safety["firmware_written"])
        self.assertFalse(safety["option_bytes_written"])

        not_qualified = set(a["scope_boundary"]["not_qualified"])
        self.assertIn("BEACON", not_qualified)
        self.assertIn("BTEXT", not_qualified)
        self.assertIn("ID", not_qualified)
        self.assertIn("connected-mode CONNECT behavior", not_qualified)
        self.assertIn("persistent TX enablement", not_qualified)

        self.assertEqual(d["status"], "target-pi-physical-tx-qualified")
        self.assertTrue(d["p4_complete"])
        self.assertEqual(blob(ACCEPTANCE), EXPECTED_ACCEPTANCE_BLOB)
        self.assertEqual(blob(EVIDENCE), EXPECTED_EVIDENCE_BLOB)
        self.assertEqual(blob(PHYSICAL_CONTRACT), EXPECTED_PHYSICAL_CONTRACT_BLOB)

        print("YWD1278_0F_P4_FINAL_ACCEPTANCE=PASS")
        print("P4_PHYSICALLY_QUALIFIED=YES")
        print("CLASSIC_CONVERSE_TX_LINES=1")
        print("INTERNAL_TX_DISPATCHES=1")
        print("INDEPENDENT_EXACT_DECODE_COUNT=1")
        print("POST_TX_RX_RESUMED=YES")
        print("PERSISTENT_TX_ENABLED=NO")
        print("NORMAL_SERVICE_RESTORED=YES")
        print("LATER_TX_FEATURES_DEFERRED=YES")


if __name__ == "__main__":
    unittest.main(verbosity=2)
