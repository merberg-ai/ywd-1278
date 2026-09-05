#!/usr/bin/env python3
"""Evidence contract for the authorized but not-yet-transmitted 0F-P4 stage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p4-classic-tx-pre-rf.json"
EXPECTED_RUNTIME_BLOBS = {
    "tools/qualify_0f_p4_classic_tx.py": "8ed7ea78b332539e8db48288bc96dfc14c31f23d",
    "tests/classic_tx_0f_p4_harness_test.py": "76087b66e18355a3f95b95c8d5937a30350d3c8d",
    "tests/classic_tx_0f_p4_safety_contract_test.py": "b72f205a55809fafa7a6cc056eb3b048d1315910",
}
HISTORICAL_STAGING_WORKFLOW_BLOB = "ea325d0172f944519f5b70c4cab0d0ec606cb14a"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicTX0FP4PreRFEvidenceTests(unittest.TestCase):
    def test_authorized_pre_rf_stage_is_exact_and_unconsumed(self) -> None:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["stage"], "0F-P4")
        self.assertEqual(data["status"], "pre-rf-staged-authorized")
        self.assertEqual(
            data["base"]["host_sha"],
            "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3",
        )
        staging = data["staging"]
        self.assertEqual(staging["implementation_head"], "22bb40da367b575c0c81e02b604080c1cae67aad")
        self.assertEqual(staging["ci_run_id"], 33939208615)
        self.assertEqual(staging["ci_conclusion"], "success")
        self.assertEqual(staging["harness_blob"], EXPECTED_RUNTIME_BLOBS["tools/qualify_0f_p4_classic_tx.py"])
        self.assertEqual(staging["harness_test_blob"], EXPECTED_RUNTIME_BLOBS["tests/classic_tx_0f_p4_harness_test.py"])
        self.assertEqual(staging["safety_contract_blob"], EXPECTED_RUNTIME_BLOBS["tests/classic_tx_0f_p4_safety_contract_test.py"])
        self.assertEqual(staging["workflow_blob"], HISTORICAL_STAGING_WORKFLOW_BLOB)

        auth = data["operator_authorization"]
        self.assertTrue(auth["authorized"])
        self.assertFalse(auth["authorization_consumed"])
        self.assertEqual(auth["authorization_token"], "0F-P4-TX-145050-ONE")
        self.assertFalse(auth["persistent_tx_authorized"])
        self.assertFalse(auth["automatic_tx_authorized"])
        self.assertFalse(auth["beacon_tx_authorized"])
        self.assertFalse(auth["connected_mode_tx_authorized"])
        self.assertFalse(auth["firmware_write_authorized"])

        vector = data["fixed_vector"]
        self.assertEqual(vector["source"], "KJ6YWD-10")
        self.assertEqual(vector["destination"], "YWD127")
        self.assertEqual(vector["path"], [])
        self.assertEqual(vector["information"], "YWD-1278 0F-P4 CLASSIC TX 1/1")
        self.assertEqual(vector["frequency_hz"], 145050000)
        self.assertEqual(vector["tx_power"], 200)
        self.assertEqual(vector["classic_converse_tx_lines_max"], 1)
        self.assertEqual(vector["kiss_tx_messages"], 0)
        self.assertEqual(vector["internal_tx_dispatches_max"], 1)
        self.assertFalse(vector["automatic_retry"])

        physical = data["physical"]
        self.assertFalse(physical["target_pi_modified_by_staging"])
        self.assertFalse(physical["service_mutated_by_staging"])
        self.assertFalse(physical["modem_uart_opened_by_staging"])
        self.assertFalse(physical["classic_tx_line_sent"])
        self.assertFalse(physical["kiss_data_sent"])
        self.assertFalse(physical["rf_transmitted"])
        self.assertFalse(physical["firmware_written"])
        self.assertFalse(physical["option_bytes_written"])
        self.assertFalse(physical["p4_qualified"])

        for relative, expected in EXPECTED_RUNTIME_BLOBS.items():
            with self.subTest(path=relative):
                self.assertEqual(blob(ROOT / relative), expected)

        print("YWD1278_0F_P4_PRE_RF_EVIDENCE=PASS")
        print("OPERATOR_AUTHORIZED=YES")
        print("AUTHORIZATION_CONSUMED=NO")
        print("CLASSIC_TX_LINES_MAX=1")
        print("KISS_TX_MESSAGES=0")
        print("RF_TRANSMITTED=NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
