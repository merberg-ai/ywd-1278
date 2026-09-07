#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "installer/persistent-bbs-config-bootstrap.sh"


class PersistentBBSConfigBootstrapP5Contract(unittest.TestCase):
    def test_dry_run_is_zero_io(self) -> None:
        output = subprocess.check_output(
            ["bash", str(BOOTSTRAP), "--dry-run"], cwd=ROOT, text=True
        )
        for marker in (
            "YWD1278_0I_P5_CONFIG_BOOTSTRAP_DRY_RUN=PASS",
            "PERSISTENT_CONFIG_MUTATED=NO",
            "SYSTEMD_MUTATED=NO",
            "MODEM_UART_OPENED=NO",
            "RF_TRANSMITTED=NO",
            "FLASH_WRITTEN=NO",
            "OPTION_BYTES_WRITTEN=NO",
        ):
            self.assertIn(marker, output)

    def test_bootstrap_is_bounded_to_missing_node_mailbox_profile(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("has_node='node' in root", text)
        self.assertIn("has_mailbox='mailbox' in root", text)
        self.assertIn("if has_node != has_mailbox", text)
        self.assertIn("if has_node:", text)
        self.assertIn("[node]\\nenabled = false", text)
        self.assertIn('alias = "YWDNOD"', text)
        self.assertIn("max_sessions = 1", text)
        self.assertIn("[mailbox]\\nenabled = false", text)
        self.assertIn('database = "/var/lib/ywd-1278/mailbox.sqlite3"', text)
        self.assertIn("paclen = 128", text)
        self.assertIn("load_product_packet_engine_config(out)", text)
        self.assertIn("load_product_node_mailbox_config(out)", text)

    def test_bootstrap_requires_exact_safe_physical_profile(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        for required in (
            "KJ6YWD",
            "145_050_000",
            "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021",
            "persistent TX must be disabled before config bootstrap",
            "beacon must remain disabled",
            "forwarding must remain disabled",
            "allow_automatic_flash",
        ):
            self.assertIn(required, text)

    def test_bootstrap_has_no_service_modem_tx_or_firmware_path(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        for forbidden in (
            "systemctl ",
            "/dev/tty",
            "/dev/serial",
            "KISSMessage(",
            "submit_frame(",
            "ThreadSafeKISSDataAdmissionQueue",
            "ShadowChannelAccessAttempt",
            "product-tx-control.sh",
            "stm32flash",
            "hardware-detect.sh",
            "deploy-product-firmware.sh",
            "hat_control.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
