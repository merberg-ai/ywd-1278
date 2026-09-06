#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ywd1278.service.node_mailbox_config import (
    DEFAULT_MAILBOX_DATABASE,
    ProductNodeMailboxConfigurationError,
    load_product_node_mailbox_config,
)


class NodeMailboxConfigP3Tests(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="ywd-0i-p3-"))
        path = directory / "config.toml"
        path.write_text(text, encoding="ascii")
        self.addCleanup(lambda: directory.rmdir())
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_missing_tables_are_safe_disabled_defaults(self) -> None:
        config = load_product_node_mailbox_config(self.write("[station]\ncallsign='N0CALL'\nssid=0\n"))
        self.assertFalse(config.node_enabled)
        self.assertFalse(config.mailbox_enabled)
        self.assertIsNone(config.local)
        self.assertEqual(config.alias, "YWDNOD")
        self.assertEqual(config.max_sessions, 1)
        self.assertEqual(config.mailbox_database, DEFAULT_MAILBOX_DATABASE)
        self.assertEqual(config.mailbox_paclen, 128)

    def test_enabled_pair_resolves_station_identity_and_mailbox(self) -> None:
        config = load_product_node_mailbox_config(
            self.write(
                """
[station]
callsign="KJ6YWD"
ssid=10
[node]
enabled=true
alias="ywdnod"
max_sessions=1
[mailbox]
enabled=true
database="/var/lib/ywd-1278/mailbox.sqlite3"
paclen=128
info="KJ6YWD packet mailbox"
[storage]
database="/var/lib/ywd-1278/ywd-1278.sqlite3"
"""
            )
        )
        self.assertTrue(config.node_enabled)
        self.assertTrue(config.mailbox_enabled)
        self.assertEqual(str(config.local), "KJ6YWD-10")
        self.assertEqual(config.alias, "YWDNOD")
        self.assertEqual(config.max_sessions, 1)
        self.assertEqual(str(config.mailbox_database), "/var/lib/ywd-1278/mailbox.sqlite3")
        self.assertEqual(config.mailbox_info, "KJ6YWD packet mailbox")

    def test_node_and_mailbox_must_enable_together(self) -> None:
        base = "[station]\ncallsign='KJ6YWD'\nssid=10\n"
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "node.enabled=true"):
            load_product_node_mailbox_config(
                self.write(base + "[node]\nenabled=false\n[mailbox]\nenabled=true\n")
            )
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "mailbox.enabled=true"):
            load_product_node_mailbox_config(
                self.write(base + "[node]\nenabled=true\n[mailbox]\nenabled=false\n")
            )

    def test_enabled_service_requires_station_identity(self) -> None:
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "requires \[station\]"):
            load_product_node_mailbox_config(
                self.write("[node]\nenabled=true\n[mailbox]\nenabled=true\n")
            )

    def test_only_single_session_is_accepted_before_sustained_qualification(self) -> None:
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "max_sessions must remain 1"):
            load_product_node_mailbox_config(
                self.write("[node]\nenabled=false\nmax_sessions=2\n")
            )

    def test_mailbox_database_must_be_absolute_and_separate(self) -> None:
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "must be an absolute path"):
            load_product_node_mailbox_config(
                self.write("[mailbox]\nenabled=false\ndatabase='mailbox.sqlite3'\n")
            )
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "must be separate"):
            load_product_node_mailbox_config(
                self.write(
                    "[storage]\ndatabase='/tmp/same.sqlite3'\n"
                    "[mailbox]\nenabled=false\ndatabase='/tmp/same.sqlite3'\n"
                )
            )

    def test_mailbox_paclen_and_info_are_bounded(self) -> None:
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "paclen must be 32..256"):
            load_product_node_mailbox_config(
                self.write("[mailbox]\nenabled=false\npaclen=257\n")
            )
        path = Path(tempfile.mkdtemp(prefix="ywd-0i-p3-unicode-")) / "config.toml"
        path.write_text('[mailbox]\nenabled=false\ninfo="café"\n', encoding="utf-8")
        self.addCleanup(lambda: path.parent.rmdir())
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        with self.assertRaisesRegex(ProductNodeMailboxConfigurationError, "info must be ASCII"):
            load_product_node_mailbox_config(path)

    def test_example_configuration_remains_disabled_and_separate(self) -> None:
        config = load_product_node_mailbox_config(Path("config/ywd-1278.example.toml"))
        self.assertFalse(config.node_enabled)
        self.assertFalse(config.mailbox_enabled)
        self.assertEqual(str(config.mailbox_database), "/var/lib/ywd-1278/mailbox.sqlite3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
