#!/usr/bin/env python3
"""Physical evidence contract for 0F-P8 sustained product CONVERSE qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p8-sustained-product-converse-target-pi.json"
DOC = ROOT / "docs/qualifications/0f-p8-sustained-product-converse-physical-qualified-2026-09-06.md"
TOOL = ROOT / "tools/qualify_0f_p8_sustained_converse.py"
STAGING_CONTRACT = ROOT / "tests/classic_tx_converse_0f_p8_physical_staging_contract_test.py"
P7_EVIDENCE = ROOT / "firmware/qualification/0f-p7-product-converse-target-pi.json"
P7_CONTRACT = ROOT / "tests/classic_tx_product_converse_0f_p7_physical_evidence_contract_test.py"
P7_DOC = ROOT / "docs/qualifications/0f-p7-product-converse-physical-qualified-2026-09-06.md"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class SustainedProductConverse0FP8PhysicalEvidenceTests(unittest.TestCase):
    def test_exact_physical_result(self) -> None:
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(d["schema"], 1)
        self.assertEqual(d["stage"], "0F-P8")
        self.assertEqual(d["status"], "target-pi-physical-sustained-product-converse-qualified")
        self.assertEqual(d["qualified_on"], "2026-09-06")

        tested = d["tested_source"]
        self.assertEqual(tested["branch"], "dev-0f-p8-sustained-product-converse")
        self.assertEqual(tested["commit"], "ec308286ae5d7ac8de5c45e782b14e3a87db96f6")

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

        unproto = d["unproto"]
        self.assertEqual(unproto["destination"], "JIM")
        self.assertEqual(unproto["path"], ["YWDNOD"])

        vectors = d["qualified_vectors"]
        self.assertEqual(len(vectors), 3)
        for n, vector in enumerate(vectors, start=1):
            self.assertEqual(vector["information"], f"YWD-1278 P8 CONVERSE {n}/3")
            self.assertEqual(
                vector["expected_external_decode"],
                f"KJ6YWD-10>JIM,YWDNOD:YWD-1278 P8 CONVERSE {n}/3",
            )

        q = d["qualified_behavior"]
        self.assertTrue(q["product_converse_entered"])
        self.assertTrue(q["command_prompt_suppressed"])
        self.assertTrue(q["live_rx_subscriber_attached"])
        self.assertEqual(q["product_converse_tx_lines"], 3)
        self.assertTrue(q["independent_external_decode_confirmed"])
        self.assertEqual(q["independent_external_decode_count"], 3)
        self.assertTrue(q["same_session_live_rx"])
        self.assertEqual(
            q["same_session_live_rx_line"],
            "RX KJ6YWD-10>JIM,YWDNOD*:YWD-1278 P8 CONVERSE 2/3",
        )
        self.assertTrue(q["printable_cmd_escape"])
        self.assertTrue(q["command_prompt_restored"])
        self.assertEqual(q["tx_dispatches"], 3)
        self.assertEqual(q["tx_queue_accepted"], 3)
        self.assertEqual(q["tx_queue_dispatched"], 3)
        self.assertEqual(q["subscriber_drops"], 0)
        self.assertTrue(q["no_second_internal_dispatch_after_hold"])
        self.assertFalse(q["automatic_tx_retry"])
        self.assertTrue(q["ctrl_c_escape"])
        self.assertTrue(q["ctrl_c_partial_line_discard"])
        self.assertEqual(q["ctrl_c_additional_tx"], 0)

        safety = d["final_safety_state"]
        self.assertFalse(safety["persistent_tx_enabled"])
        self.assertFalse(safety["persistent_config_mutated"])
        self.assertFalse(safety["installed_source_mutated"])
        self.assertTrue(safety["normal_service_restored"])
        self.assertFalse(safety["firmware_written"])
        self.assertFalse(safety["option_bytes_written"])

    def test_exact_staged_inputs_and_p7_history_remain_frozen(self) -> None:
        self.assertEqual(blob(EVIDENCE), "2a60963f0809cb01b5dd52486be79145dcff768d")
        self.assertEqual(blob(DOC), "de46bf80275547a43668c08a333a0d5a5207ac8d")
        self.assertEqual(blob(TOOL), "985990dd4395804f605d9c4bde2b8864c46fc05d")
        self.assertEqual(blob(STAGING_CONTRACT), "13ddde075f3cab4b70a6db67b166f64a85e73135")
        self.assertEqual(blob(P7_EVIDENCE), "0dbb37953e50d6e7c4ae6a2064e1197794207eef")
        self.assertEqual(blob(P7_CONTRACT), "a8cdf768d46e6be3bfcd9a6c50506fce42f85659")
        self.assertEqual(blob(P7_DOC), "72f24a241a30e09e85a3c2626ec4e7b218c87489")

    def test_scope_boundary_is_explicit(self) -> None:
        d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        qualified = set(d["scope_boundary"]["qualified"])
        self.assertIn("three-line sustained permanent product Telnet CONVERSE transmission", qualified)
        self.assertIn("UNPROTO destination JIM with VIA YWDNOD", qualified)
        self.assertIn("physical raw Ctrl-C escape", qualified)
        self.assertIn("discard of an unfinished partial CONVERSE line on Ctrl-C", qualified)
        self.assertIn("zero additional TX caused by Ctrl-C", qualified)

        not_qualified = set(d["scope_boundary"]["not_qualified_by_this_slice"])
        self.assertIn("persistent TX enablement", not_qualified)
        self.assertIn("arbitrary unbounded sustained converse operation", not_qualified)
        self.assertIn("multiple or chained digipeater paths beyond YWDNOD", not_qualified)
        self.assertIn("BEACON/BTEXT/ID RF behavior", not_qualified)
        self.assertIn("connected-mode CONNECT behavior", not_qualified)

        text = DOC.read_text(encoding="utf-8")
        self.assertIn("PHYSICALLY QUALIFIED", text)
        self.assertIn("ec308286ae5d7ac8de5c45e782b14e3a87db96f6", text)
        self.assertIn("YWD1278_0F_P8_SUSTAINED_PRODUCT_CONVERSE_PHYSICAL=PASS", text)
        self.assertIn("NORMAL_SERVICE_RESTORED=YES", text)

        print("YWD1278_0F_P8_SUSTAINED_PRODUCT_CONVERSE_PHYSICAL_EVIDENCE=PASS")
        print("PRODUCT_CONVERSE_TX_LINES=3")
        print("INDEPENDENT_EXTERNAL_DECODE_COUNT=3")
        print("VIA_YWDNOD=QUALIFIED")
        print("SAME_SESSION_LIVE_RX=PASS")
        print("PRINTABLE_CMD_ESCAPE=PASS")
        print("CTRL_C_ESCAPE=PASS")
        print("CTRL_C_PARTIAL_LINE_DISCARD=PASS")
        print("CTRL_C_ADDITIONAL_TX=0")
        print("AUTOMATIC_TX_RETRY=NO")
        print("PERSISTENT_TX_ENABLED=NO")
        print("NORMAL_SERVICE_RESTORED=YES")
        print("FROZEN_0F_P7_EVIDENCE=UNCHANGED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
