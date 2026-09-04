#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from ywd1278.install.readiness import (
    EXIT_INCOMPLETE,
    EXIT_READY,
    EXIT_UNSAFE,
    INCOMPLETE,
    READY,
    UNSAFE,
    inspect_runtime_readiness,
    main,
)
from ywd1278.service.appliance import PRODUCT_TARGET


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config/ywd-1278.example.toml"


def ready_text() -> str:
    text = EXAMPLE.read_text(encoding="utf-8")
    text = text.replace('callsign = "N0CALL"', 'callsign = "KJ6YWD"')
    text = text.replace('target = ""', f'target = "{PRODUCT_TARGET}"')
    text = text.replace("frequency_mhz = 0.0", "frequency_mhz = 145.050")
    return text


def write_config(directory: str, text: str, name: str = "config.toml") -> Path:
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return path


class InstallerRuntimeStageETests(unittest.TestCase):
    def test_safe_example_is_incomplete_not_unsafe(self) -> None:
        result = inspect_runtime_readiness(EXAMPLE)
        self.assertEqual(result.status, INCOMPLETE)
        self.assertEqual(result.exit_code, EXIT_INCOMPLETE)
        self.assertIn("STATION_CALLSIGN", result.reasons)
        self.assertIn("HARDWARE_TARGET", result.reasons)
        self.assertIn("RADIO_FREQUENCY", result.reasons)
        self.assertNotIn("TX_ENABLED", result.reasons)
        self.assertNotIn("AUTO_FLASH_ENABLED", result.reasons)

    def test_complete_product_profile_is_ready_with_no_hardware_io(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = write_config(td, ready_text())
            with patch("os.open", side_effect=AssertionError("os.open must not be called")):
                with patch.object(socket, "socket", side_effect=AssertionError("socket must not open")):
                    result = inspect_runtime_readiness(path)
            self.assertEqual(result.status, READY)
            self.assertEqual(result.exit_code, EXIT_READY)
            self.assertEqual(result.reasons, ())

    def test_tx_enabled_is_unsafe_even_when_everything_else_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text = ready_text().replace("tx_enabled = false", "tx_enabled = true")
            result = inspect_runtime_readiness(write_config(td, text))
            self.assertEqual(result.status, UNSAFE)
            self.assertEqual(result.exit_code, EXIT_UNSAFE)
            self.assertIn("TX_ENABLED", result.reasons)

    def test_automatic_flash_is_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text = ready_text().replace(
                "allow_automatic_flash = false", "allow_automatic_flash = true"
            )
            result = inspect_runtime_readiness(write_config(td, text))
            self.assertEqual(result.status, UNSAFE)
            self.assertIn("AUTO_FLASH_ENABLED", result.reasons)

    def test_public_console_bind_is_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text = ready_text().replace(
                'listen = "127.0.0.1"\nport = 8010',
                'listen = "0.0.0.0"\nport = 8010',
            )
            result = inspect_runtime_readiness(write_config(td, text))
            self.assertEqual(result.status, UNSAFE)
            self.assertTrue(any(reason.startswith("CONSOLE_CONFIG:") for reason in result.reasons))

    def test_missing_private_lan_auth_file_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            auth = Path(td) / "missing-console.auth"
            text = ready_text().replace(
                'listen = "127.0.0.1"\nport = 8010',
                f'listen = "192.168.1.11"\nport = 8010\nauth_file = "{auth}"',
            )
            result = inspect_runtime_readiness(write_config(td, text))
            self.assertEqual(result.status, INCOMPLETE)
            self.assertIn("CONSOLE_AUTH_FILE_MISSING", result.reasons)

    def test_kiss_console_port_collision_is_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            text = ready_text().replace("port = 8010", "port = 8001")
            result = inspect_runtime_readiness(write_config(td, text))
            self.assertEqual(result.status, UNSAFE)
            self.assertIn("KISS_CONSOLE_PORT_COLLISION", result.reasons)

    def test_cli_markers_are_deterministic_and_zero_io(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = write_config(td, ready_text())
            output = io.StringIO()
            with redirect_stdout(output):
                rc = main(["--config", str(path)])
            self.assertEqual(rc, EXIT_READY)
            lines = output.getvalue().splitlines()
            self.assertIn("YWD1278_INSTALL_RUNTIME_READINESS=READY", lines)
            self.assertIn("MODEM_UART_OPENED=NO", lines)
            self.assertIn("RF_TRANSMITTED=NO", lines)
            self.assertIn("FLASH_WRITTEN=NO", lines)
            self.assertIn("READINESS_REASON=NONE", lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
