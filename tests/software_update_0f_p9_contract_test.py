#!/usr/bin/env python3
"""Pre-live safety contract for the 0F-P9 software-only installed updater."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "installer/update-installed-software.sh"


class SoftwareUpdateP9ContractTests(unittest.TestCase):
    def test_dry_run_is_zero_io(self) -> None:
        proc = subprocess.run(
            ["bash", str(UPDATER), "--dry-run"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        out = proc.stdout
        self.assertIn("YWD1278_0F_P9_SOFTWARE_UPDATE_DRY_RUN=PASS", out)
        self.assertIn("PERSISTENT_TX_REQUIRED=DISABLED", out)
        self.assertIn("INSTALLED_SOURCE_MUTATED=NO", out)
        self.assertIn("SYSTEMD_MUTATED=NO", out)
        self.assertIn("PERSISTENT_CONFIG_MUTATED=NO", out)
        self.assertIn("MODEM_UART_ACCESS=NO", out)
        self.assertIn("RF_TRANSMITTED=NO", out)
        self.assertIn("FLASH_WRITTEN=NO", out)
        self.assertIn("OPTION_BYTES_WRITTEN=NO", out)

    def test_exact_source_and_clean_tree_are_required(self) -> None:
        text = UPDATER.read_text(encoding="utf-8")
        self.assertIn("--expected-source-commit", text)
        self.assertIn('actual_source_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"', text)
        self.assertIn("checkout commit mismatch", text)
        self.assertIn("tracked source tree is dirty", text)

    def test_update_requires_persistent_tx_disabled(self) -> None:
        text = UPDATER.read_text(encoding="utf-8")
        self.assertIn("persistent TX must be disabled before software update", text)
        self.assertIn("radio.tx_enabled", text)
        self.assertIn("PERSISTENT_TX_ENABLED=NO", text)

    def test_update_is_software_only(self) -> None:
        text = UPDATER.read_text(encoding="utf-8").lower()
        self.assertNotIn("hardware-detect", text)
        self.assertNotIn("setup-hat", text)
        self.assertNotIn("deploy-product-firmware", text)
        self.assertNotIn("stm32flash", text)
        self.assertNotIn("hat_control.py", text)
        self.assertNotIn("firmware_trust", text)
        self.assertNotIn("/dev/ttyama0", text)
        self.assertIn("firmware_action=no", text)
        self.assertIn("modem_uart_access=no", text)

    def test_candidate_is_built_before_service_stop(self) -> None:
        text = UPDATER.read_text(encoding="utf-8")
        wheel = text.index("pip wheel")
        stop = text.index('systemctl stop "$SERVICE"')
        self.assertLess(wheel, stop)

    def test_rollback_restores_source_venv_unit_and_commit(self) -> None:
        text = UPDATER.read_text(encoding="utf-8")
        self.assertIn("restoring pre-P9 installed software", text)
        self.assertIn('mv "$source_backup" "$SOURCE_ROOT"', text)
        self.assertIn('mv "$venv_backup" "$VENV"', text)
        self.assertIn('cp -a "$unit_backup" "$UNIT_INSTALLED"', text)
        self.assertIn('cp -a "$commit_backup" "$INSTALL_ROOT/installed-commit"', text)

    def test_updater_never_mutates_persistent_config(self) -> None:
        text = UPDATER.read_text(encoding="utf-8")
        self.assertNotIn('>"$CONFIG"', text)
        self.assertNotIn('mv "$CONFIG', text)
        self.assertNotIn('cp "$CONFIG', text)
        self.assertIn("CONFIG_MUTATED=NO", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
