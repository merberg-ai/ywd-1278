#!/usr/bin/env python3
"""Static product-composition contract for live classic converse sessions."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "src/ywd1278/daemon.py"
CONVERSE = ROOT / "src/ywd1278/service/product_converse_console.py"
MAILBOX_CONSOLE = ROOT / "src/ywd1278/service/product_mailbox_console.py"
SESSION = ROOT / "src/ywd1278/console/product_session.py"
MONITOR_STREAM = ROOT / "src/ywd1278/monitor/stream.py"
FROZEN_MONITOR_STREAM_BLOB = "703b7e803d39d915b60d79c30c154151e3820098"


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ProductConverseCompositionContractTests(unittest.TestCase):
    def test_daemon_reuses_one_product_backend_for_tx_and_live_rx(self) -> None:
        text = DAEMON.read_text(encoding="utf-8")
        mailbox_text = MAILBOX_CONSOLE.read_text(encoding="utf-8")
        self.assertIn("make_product_backend_submitter(lambda: engine.backend)", text)
        self.assertIn("ProductClassicMailboxConsole(", text)
        self.assertIn(
            "class ProductClassicMailboxConsole(ProductClassicConverseConsole):",
            mailbox_text,
        )
        self.assertIn(
            "live_monitor_factory=lambda: open_live_only_monitor(engine.backend)",
            text,
        )
        self.assertNotIn("ProductClassicTXConsole(", text)

    def test_live_rx_borrows_existing_bounded_backend_subscription(self) -> None:
        text = CONVERSE.read_text(encoding="utf-8")
        self.assertIn("history, live_queue = backend.open_stream()", text)
        self.assertIn("LiveOnlyMonitorSubscription(", text)
        self.assertIn("self._live_queue.get_nowait()", text)
        self.assertIn("_decode_event(", text)
        self.assertIn("self._backend.close_stream(self._live_queue)", text)
        self.assertIn("subscription.read_available(maximum=maximum)", text)
        self.assertIn("subscription.close()", text)
        self.assertNotIn("Queue(", text)
        self.assertNotIn("deque(", text)

    def test_frozen_0d_monitor_stream_is_unchanged(self) -> None:
        self.assertEqual(git_blob(MONITOR_STREAM), FROZEN_MONITOR_STREAM_BLOB)

    def test_converse_layers_do_not_import_hardware_or_channel_access_owners(self) -> None:
        forbidden_prefixes = (
            "ywd1278.modem",
            "ywd1278.channel_access",
            "ywd1278.csma",
            "serial",
            "RPi",
        )
        for path in (CONVERSE, SESSION):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            for imported in imports:
                self.assertFalse(
                    imported.startswith(forbidden_prefixes),
                    f"{path.name} unexpectedly imports {imported}",
                )

    def test_product_transport_hooks_are_opt_in_subclasses(self) -> None:
        text = SESSION.read_text(encoding="utf-8")
        self.assertIn("class ProductTelnetTNCServer(TelnetTNCServer):", text)
        self.assertIn(
            "class ProductAuthenticatedLanTNCServer(AuthenticatedLanTNCServer):",
            text,
        )
        self.assertIn("class ProductVirtualPTYTNC(VirtualPTYTNC):", text)
        self.assertIn("data.split(b\"\\x03\")", text)
        self.assertIn("session_control_etx", text)
        self.assertIn("session_drain_output", text)
        self.assertIn("session_close", text)

    def test_converse_escape_and_history_policy_are_explicit(self) -> None:
        text = CONVERSE.read_text(encoding="utf-8")
        self.assertIn('normalized.upper() == "/CMD"', text)
        self.assertIn('line = "COMMAND"', text)
        self.assertIn("del history", text)
        self.assertIn("PRE-CONVERSE HISTORY NOT REPLAYED", text)
        self.assertIn("return not self.tx_snapshot.converse_mode", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
