#!/usr/bin/env python3
"""Sealed host-qualification evidence contract for 0F P1/P2/P3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/qualification/0f-classic-unproto-converse-host.json"

EXPECTED_BLOBS = {
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/daemon.py": "ce1ba6af92f7238ab1a1ac0aca268a94c4fa515b",
    "tests/classic_tnc_tx_0f_test.py": "5feb2b3851f6e5d81eb79e8d490a53407b097a82",
    "tests/product_classic_tx_0f_test.py": "b70ba6cf188725c05f0533a882e0f656211ff5da",
    "tests/product_classic_tx_daemon_0f_test.py": "3db15806094945408075be355805dc3ec04865a4",
    "tests/classic_tx_0f_contract_test.py": "aa160b96f023e14ea9bf68d7eda764cfb3410fdd",
    ".github/workflows/0f-classic-tx-ci.yml": "4cfc3358f6e0280412f0dfa517509d93c781d83a",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ClassicTX0FHostQualificationContractTests(unittest.TestCase):
    def test_sealed_host_qualification(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["stage"], "0F")
        self.assertEqual(data["status"], "host-qualified-physical-tx-pending")
        self.assertEqual(
            data["base_appliance"]["sha"],
            "e9fc1c4e3810bb7ed63ffd3417d2f3958cd9d1ca",
        )
        self.assertEqual(
            data["development"]["implementation_head"],
            "ef2f630844e12f7d5ff68e25695a95b0fb84fce0",
        )
        self.assertEqual(data["development"]["ci_run_id"], 33938085041)
        self.assertEqual(data["development"]["ci_conclusion"], "success")
        self.assertEqual(data["implementation_blobs"], EXPECTED_BLOBS)

        self.assertTrue(data["p1_unproto"]["qualified"])
        self.assertTrue(data["p2_converse"]["qualified"])
        self.assertTrue(data["p3_product_composition"]["qualified"])
        self.assertTrue(
            data["p3_product_composition"]["persistent_tx_disabled_fails_closed_before_submit"]
        )
        self.assertEqual(data["p3_product_composition"]["fake_hat_tx_enabled_dispatches"], 1)
        self.assertTrue(data["p3_product_composition"]["fake_hat_rx_restarted_after_tx"])
        self.assertTrue(data["p3_product_composition"]["no_second_dispatch_hold"])
        self.assertFalse(data["p3_product_composition"]["kiss_tcp_listener_required_for_console_tx"])

        self.assertTrue(all(data["preserved_boundaries"].values()))
        physical = data["physical"]
        self.assertFalse(physical["target_pi_modified"])
        self.assertFalse(physical["installed_appliance_modified"])
        self.assertFalse(physical["modem_uart_opened"])
        self.assertFalse(physical["rf_transmitted"])
        self.assertFalse(physical["firmware_written"])
        self.assertFalse(physical["physical_0f_tx_authorized"])
        self.assertFalse(physical["physical_0f_tx_qualified"])

        for relative, expected in EXPECTED_BLOBS.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

        print("YWD1278_0F_HOST_QUALIFICATION=PASS")
        print("P1_UNPROTO=PASS")
        print("P2_CONVERSE=PASS")
        print("P3_PRODUCT_COMPOSITION=PASS")
        print("PHYSICAL_TX_AUTHORIZED=NO")
        print("RF_TRANSMITTED=NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
