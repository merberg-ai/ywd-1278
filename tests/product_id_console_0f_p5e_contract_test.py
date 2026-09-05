#!/usr/bin/env python3
"""Architecture and lineage contract for the 0F-P5e manual ID command."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/service/product_beacon_console.py": "5b21ba853c978e9c3e268e47ca6fb24a7f6aa081",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "tools/qualify_0f_p5d_beacon.py": "ec2873ab432a9bfee1470a11c5aac29c6099d55f",
    "firmware/qualification/0f-p5d-beacon-target-pi.json": "d9fb4ed8d41c777dfa65e0a6188c2c45cc60def4",
    "tests/classic_beacon_0f_p5d_physical_evidence_contract_test.py": "5811c1b0c366944f82278cdf6d39a0ccf8b898a9",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductIDConsoleP5eContractTests(unittest.TestCase):
    def test_p5d_evidence_and_existing_owners_are_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_id_is_fixed_direct_and_uses_one_existing_submitter_call(self) -> None:
        text = (ROOT / "src/ywd1278/service/product_id_console.py").read_text(encoding="utf-8")
        self.assertIn('ID_DESTINATION = Address.parse("ID")', text)
        self.assertIn('ID_TEXT_PREFIX = "YWD-1278 ID "', text)
        self.assertIn("path=(),", text)
        self.assertIn("include_fcs=False,", text)
        self.assertEqual(text.count("result = submitter(frame_no_fcs)"), 1)

    def test_id_layer_has_no_timer_hardware_or_second_tx_graph(self) -> None:
        text = (ROOT / "src/ywd1278/service/product_id_console.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading.Timer", "ProductBeaconScheduler(", "KISSMessage(",
            "reject_client_message", "TXModemOwner(", "PosixSerialTransport(",
            "ShadowChannelAccessAttempt(", "RPi.GPIO", "time.sleep(",
        ):
            self.assertNotIn(forbidden, text)

    def test_daemon_selects_id_console_without_adding_a_submitter(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertEqual(daemon.count("ProductClassicIDConsole("), 1)
        self.assertEqual(daemon.count("make_product_backend_submitter("), 1)
        self.assertEqual(daemon.count("ThreadSafeProductBeaconCoordinator("), 1)
        self.assertIn("tx_submitter=submitter", daemon)
        self.assertIn("beacon=beacon", daemon)

    def test_persistent_beacon_gate_remains_closed(self) -> None:
        appliance = (ROOT / "src/ywd1278/service/appliance.py").read_text(encoding="utf-8")
        self.assertIn(
            'raise ProductConfigurationError("beacon.enabled requires future 0F qualification")',
            appliance,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
