#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "installer/persistent-bbs-physical-control.sh"
STAGING = ROOT / "docs/qualifications/0i-p5-persistent-bbs-physical-staging.md"

FROZEN_P4C2 = {
    "src/ywd1278/daemon.py": "85471ccac9e26079c0265753054d54eb1753e191",
    "src/ywd1278/service/product_mailbox_console.py": "93c9a66be6b5d01d6bacfb70b2eef7b1189a9b6c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/persistent_bbs_service.py": "b816e786de1ca3acaeb1201857bf36db2d008dcf",
    "src/ywd1278/node/persistent_bbs_runtime.py": "0c40aaf283142b71d16c9f30a1687865a98b197f",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
}


class PersistentBBSPhysicalStagingP5Contract(unittest.TestCase):
    def test_p4c2_runtime_remains_exactly_frozen(self) -> None:
        for path, expected in FROZEN_P4C2.items():
            with self.subTest(path=path):
                actual = subprocess.check_output(
                    ["git", "hash-object", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(actual, expected)

    def test_control_stages_only_node_mailbox_and_reuses_tx_gate(self) -> None:
        text = CONTROL.read_text(encoding="utf-8")
        self.assertIn("replace_bool(text,'node','enabled',enabled)", text)
        self.assertIn("replace_bool(text,'mailbox','enabled',enabled)", text)
        self.assertNotIn("replace_bool(text,'radio'", text)
        self.assertIn('"$TX_CONTROL" disable --expected-installed-commit "$installed_commit"', text)
        self.assertNotIn('"$TX_CONTROL" enable', text)
        self.assertIn("NEXT_STEP=RUN_EXISTING_0F_P9_TX_ENABLE_CONTROL", text)
        self.assertIn("PERSISTENT_TX_ENABLED=NO", text)
        self.assertIn("SERVICE_ACTIVE=NO", text)

    def test_cleanup_revokes_tx_before_disabling_node_and_restarting_service(self) -> None:
        text = CONTROL.read_text(encoding="utf-8")
        cleanup = text.index("# CLEANUP")
        stop = text.index('systemctl stop "$SERVICE"', cleanup)
        revoke = text.index('"$TX_CONTROL" disable', stop)
        render_disabled = text.index('render_candidate false "$candidate"', revoke)
        restore = text.index('systemctl start "$SERVICE"', render_disabled)
        self.assertLess(stop, revoke)
        self.assertLess(revoke, render_disabled)
        self.assertLess(render_disabled, restore)

    def test_control_has_no_alternate_modem_firmware_or_frame_path(self) -> None:
        text = CONTROL.read_text(encoding="utf-8")
        for token in (
            "/dev/tty",
            "/dev/serial",
            "KISSMessage(",
            "submit_frame(",
            "ShadowChannelAccessAttempt",
            "ThreadSafeKISSDataAdmissionQueue",
            "stm32flash",
            "hat_control.py",
            "hardware-detect.sh",
            "deploy-product-firmware.sh",
            "option-byte",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, text)

    def test_staging_document_fixes_the_physical_scope(self) -> None:
        text = STAGING.read_text(encoding="utf-8")
        for required in (
            "dd2f96f27050bf24c57e24a9b2b3a2ba86688b27",
            "KJ6YWD-10",
            "145.050 MHz",
            "TX power: `200/255`",
            "node alias: `YWDNOD`",
            "Connected BBS qualification is direct only",
            "update-installed-software.sh",
            "product-tx-control.sh",
            "PERSISTENT_BBS=ENABLED",
            "MBOX=ENABLED",
            "FORWARDING=DISABLED",
            "RF-created message is visible in local MBOX",
            "mailbox SQLite database remains present",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_control_dry_run_is_zero_io(self) -> None:
        for action in ("stage", "cleanup", "status"):
            with self.subTest(action=action):
                output = subprocess.check_output(
                    ["bash", str(CONTROL), action, "--dry-run"],
                    cwd=ROOT,
                    text=True,
                )
                self.assertIn("YWD1278_0I_P5_BBS_CONTROL_DRY_RUN=PASS", output)
                self.assertIn("PERSISTENT_CONFIG_MUTATED=NO", output)
                self.assertIn("SYSTEMD_MUTATED=NO", output)
                self.assertIn("MODEM_UART_OPENED=NO", output)
                self.assertIn("RF_TRANSMITTED=NO", output)
                self.assertIn("FLASH_WRITTEN=NO", output)
                self.assertIn("OPTION_BYTES_WRITTEN=NO", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
