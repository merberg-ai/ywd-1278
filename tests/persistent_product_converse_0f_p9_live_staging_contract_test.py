#!/usr/bin/env python3
"""Contract for the manual 0F-P9 normal-service live qualification plan."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/qualifications/0f-p9-persistent-product-converse-live-staging.md"
TX_CONTROL = ROOT / "installer/product-tx-control.sh"
UPDATER = ROOT / "installer/update-installed-software.sh"
P8_EVIDENCE = ROOT / "firmware/qualification/0f-p8-sustained-product-converse-target-pi.json"


class P9ManualLiveStagingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = PLAN.read_text(encoding="utf-8")
        cls.control = TX_CONTROL.read_text(encoding="utf-8")
        cls.updater = UPDATER.read_text(encoding="utf-8")

    def test_exact_bounded_rf_vector(self) -> None:
        self.assertIn("frequency: `145.050 MHz`", self.plan)
        self.assertIn("TX power: `200/255`", self.plan)
        self.assertIn("source: `KJ6YWD-10`", self.plan)
        self.assertIn("`UNPROTO JIM VIA YWDNOD`", self.plan)
        self.assertIn("`YWD-1278 P9 PERSISTENT SERVICE 1/1`", self.plan)
        self.assertIn(
            "`KJ6YWD-10>JIM,YWDNOD:YWD-1278 P9 PERSISTENT SERVICE 1/1`",
            self.plan,
        )
        self.assertIn("maximum P9 qualification TX lines: **one**", self.plan)
        self.assertIn("No second converse text line is permitted", self.plan)

    def test_live_test_uses_normal_installed_systemd_product_surface(self) -> None:
        self.assertIn("**normal installed appliance**", self.plan)
        self.assertIn("`ywd-1278.service`", self.plan)
        self.assertIn("normal product Telnet console", self.plan)
        self.assertIn("/opt/ywd-1278/installed-commit", self.plan)
        self.assertIn("installed P9 source remains deployed", self.plan)

    def test_rx_safe_gate_precedes_tx_enable(self) -> None:
        rx_safe = self.plan.index("verify `CONVERSE` fails closed with the TX-disabled response")
        enable = self.plan.index("Explicitly enable persistent TX")
        transmit = self.plan.index("YWD-1278 P9 PERSISTENT SERVICE 1/1", enable)
        self.assertLess(rx_safe, enable)
        self.assertLess(enable, transmit)

    def test_same_session_rx_cmd_status_and_no_retry_are_required(self) -> None:
        self.assertIn("same CONVERSE session", self.plan)
        self.assertIn("Enter `/CMD`", self.plan)
        self.assertIn("Run `STATUS`", self.plan)
        self.assertIn("exactly one TX dispatch/admission/dispatch", self.plan)
        self.assertIn("no second internal dispatch", self.plan)
        self.assertIn("failed rather than retried", self.plan)
        self.assertIn("automatic TX retry: **none**", self.plan)

    def test_persistent_tx_is_disabled_after_test(self) -> None:
        disable = self.plan.index("Immediately run `installer/product-tx-control.sh disable`")
        final = self.plan.index("`tx_enabled = false`", disable)
        self.assertLess(disable, final)
        self.assertIn("`tx_power = 200`", self.plan)
        self.assertIn("`frequency_mhz = 145.050`", self.plan)

    def test_staging_uses_guarded_tools_and_preserves_frozen_p8(self) -> None:
        self.assertTrue(P8_EVIDENCE.is_file())
        self.assertIn("--expected-source-commit", self.updater)
        self.assertIn("persistent TX must be disabled before software update", self.updater)
        self.assertIn('ENABLE_AUTHORIZATION="0F-P9-PERSISTENT-PRODUCT-TX-145050"', self.control)
        self.assertIn('ENABLE_ARM_PHRASE="ENABLE-0F-P9-PERSISTENT-TX"', self.control)
        self.assertIn("FIRMWARE_FLASH=NO", self.control)
        self.assertIn("DIRECT_KISS_INJECTION=NO", self.control)

    def test_plan_never_introduces_alternate_rf_or_firmware_path(self) -> None:
        lower = self.plan.lower()
        self.assertNotIn("stm32flash", lower)
        self.assertNotIn("deploy-product-firmware", lower)
        self.assertNotIn("kiss data injection", lower)
        self.assertIn("no firmware or option-byte write occurred", lower)
        self.assertIn("no second converse text line", lower)


if __name__ == "__main__":
    unittest.main(verbosity=2)
