#!/usr/bin/env python3
"""Static safety contract for the authorized 0F-P4 physical harness."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_0f_p4_classic_tx.py"


class ClassicTX0FP4SafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text, filename=str(HARNESS))

    def test_exact_authorized_vector_and_profile_are_pinned(self) -> None:
        for token in (
            'AUTHORIZATION_TOKEN = "0F-P4-TX-145050-ONE"',
            'ARM_PHRASE = "TRANSMIT-0F-P4-ONE"',
            'DESTINATION = "YWD127"',
            'INFORMATION = "YWD-1278 0F-P4 CLASSIC TX 1/1"',
            'TEMP_KISS_PORT = 18101',
            'TEMP_CONSOLE_PORT = 18110',
            '"radio", "tx_power", str(stage_i.TX_POWER)',
            '"radio", "tx_enabled", "true"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_only_one_converse_payload_write_exists_and_command_escape_follows(self) -> None:
        tx_call = 'console_command(console, INFORMATION)'
        escape_call = 'console_command(console, "COMMAND")'
        self.assertEqual(self.text.count(tx_call), 1)
        self.assertEqual(self.text.count(escape_call), 1)
        self.assertLess(self.text.index(tx_call), self.text.index(escape_call))
        self.assertIn('console_command(console, f"UNPROTO {DESTINATION}")', self.text)
        self.assertIn('console_command(console, "CONVERSE")', self.text)

    def test_harness_never_uses_kiss_as_tx_ingress(self) -> None:
        self.assertNotIn("kiss.sendall", self.text)
        self.assertNotIn("KISSMessage(", self.text)
        self.assertNotIn("encode(", self.text)
        self.assertIn("KISS_TX_MESSAGES=0", self.text)

    def test_no_beacon_connected_mode_firmware_gpio_or_retry_authority(self) -> None:
        forbidden = (
            'console_command(console, "CONNECT',
            'console_command(console, "BEACON',
            'console_command(console, "BTEXT',
            "stm32flash",
            "flash.sh",
            "RPi.GPIO",
            "gpiozero",
            "hat_control",
            "RF_TX_TONES",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.text)
        self.assertNotIn("while True", self.text)
        self.assertNotIn("for attempt", self.text)
        self.assertNotIn("retry", self.text.lower().replace("no retry", ""))

    def test_persistent_config_is_read_and_hashed_but_never_written(self) -> None:
        self.assertIn("stage_i.PERSISTENT_CONFIG.read_bytes()", self.text)
        self.assertIn("original_hash", self.text)
        self.assertNotIn("stage_i.PERSISTENT_CONFIG.write", self.text)
        self.assertNotIn("/etc/ywd-1278/config.toml\").write", self.text)
        self.assertIn("stage_i._restore_service(original_hash)", self.text)

    def test_root_harness_pins_frozen_capability_blobs(self) -> None:
        expected = {
            "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
            "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
            "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
            "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
            "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
            "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
        }
        for path, blob in expected.items():
            with self.subTest(path=path):
                self.assertIn(f'"{path}": "{blob}"', self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
