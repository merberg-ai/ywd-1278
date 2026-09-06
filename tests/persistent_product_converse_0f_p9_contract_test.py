#!/usr/bin/env python3
"""Static/pre-live contract for 0F-P9 persistent product UNPROTO/CONVERSE activation."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "installer/product-tx-control.sh"
RX_SAFE = ROOT / "installer/enable-product-service.sh"
DAEMON = ROOT / "src/ywd1278/daemon.py"
APPLIANCE = ROOT / "src/ywd1278/service/appliance.py"
P8_EVIDENCE = ROOT / "firmware/qualification/0f-p8-sustained-product-converse-target-pi.json"


class PersistentProductConverseP9ContractTests(unittest.TestCase):
    def test_default_dry_run_has_zero_io_markers(self) -> None:
        proc = subprocess.run(
            [
                "bash",
                str(CONTROL),
                "enable",
                "--dry-run",
                "--expected-installed-commit",
                "0" * 40,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        out = proc.stdout
        self.assertIn("YWD1278_0F_P9_TX_CONTROL_DRY_RUN=PASS", out)
        self.assertIn("TX_FREQUENCY_HZ=145050000", out)
        self.assertIn("TX_POWER_ON_ENABLE=200", out)
        self.assertIn("PERSISTENT_CONFIG_MUTATED=NO", out)
        self.assertIn("SYSTEMD_MUTATED=NO", out)
        self.assertIn("MODEM_UART_OPENED=NO", out)
        self.assertIn("RF_TRANSMITTED=NO", out)
        self.assertIn("FLASH_WRITTEN=NO", out)
        self.assertIn("OPTION_BYTES_WRITTEN=NO", out)

    def test_rx_safe_activation_gate_remains_rx_only(self) -> None:
        text = RX_SAFE.read_text(encoding="utf-8")
        self.assertIn("TX must remain disabled for service activation", text)
        self.assertIn('[[ "$tx_enabled" == false ]]', text)
        self.assertNotIn("product-tx-control.sh", text)

    def test_persistent_enable_is_explicit_and_exact_profile_only(self) -> None:
        text = CONTROL.read_text(encoding="utf-8")
        self.assertIn('ENABLE_AUTHORIZATION="0F-P9-PERSISTENT-PRODUCT-TX-145050"', text)
        self.assertIn('ENABLE_ARM_PHRASE="ENABLE-0F-P9-PERSISTENT-TX"', text)
        self.assertIn("QUALIFIED_FREQUENCY_HZ=145050000", text)
        self.assertIn("QUALIFIED_POWER=200", text)
        self.assertIn("--expected-installed-commit", text)
        self.assertIn("installed source commit mismatch", text)
        self.assertIn("live HAT identity does not match exact qualified AX25R4 profile", text)
        self.assertIn("product service did not become active", text)
        self.assertIn("restoring pre-P9 persistent configuration", text)
        self.assertIn("PERSISTENT_TX_ENABLED=YES", text)

    def test_control_uses_real_product_loader_and_never_constructs_frames(self) -> None:
        text = CONTROL.read_text(encoding="utf-8")
        self.assertIn("ywd1278.install.tx_control validate", text)
        self.assertNotIn("build_ui_frame", text)
        self.assertNotIn("KISSMessage", text)
        self.assertNotIn("KISSStreamDecoder", text)
        self.assertNotIn("reject_client_message", text)
        self.assertNotIn("TX QUEUED", text)

    def test_control_has_no_firmware_write_or_retry_path(self) -> None:
        text = CONTROL.read_text(encoding="utf-8").lower()
        self.assertNotIn("stm32flash", text)
        self.assertNotIn("deploy-product-firmware", text)
        self.assertNotIn("flash_firmware", text)
        self.assertNotIn("option byte", text)
        self.assertNotIn("retry tx", text)
        self.assertIn("automatic_tx_retry=no_new_retry", text)

    def test_normal_daemon_is_already_the_p8_product_composition(self) -> None:
        text = DAEMON.read_text(encoding="utf-8")
        self.assertIn("ProductClassicConverseConsole", text)
        self.assertIn("make_product_backend_submitter", text)
        self.assertIn("live_monitor_factory=lambda: open_live_only_monitor(engine.backend)", text)
        self.assertIn('classic_0f = "ENABLED" if packet_config.tx_enabled else "TX-DISABLED"', text)

    def test_product_runtime_still_enforces_exact_tx_profile(self) -> None:
        text = APPLIANCE.read_text(encoding="utf-8")
        self.assertIn("QUALIFIED_TX_FREQUENCY_HZ = 145_050_000", text)
        self.assertIn("QUALIFIED_TX_POWER = 200", text)
        self.assertIn("product TX may only use the physically-qualified 145.050 MHz / power-200 profile", text)

    def test_p8_physical_evidence_remains_present(self) -> None:
        self.assertTrue(P8_EVIDENCE.is_file())
        self.assertGreater(P8_EVIDENCE.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
