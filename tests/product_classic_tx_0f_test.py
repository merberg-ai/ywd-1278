#!/usr/bin/env python3
"""0F P3 host tests for product classic-TX configuration/composition."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from ywd1278.ax25 import Address
from ywd1278.console.classic import ClassicTNCCommandShell
from ywd1278.console.classic_tx import ClassicTXCommandShell
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.tx_backend import KISSDataIngressResult
from ywd1278.kiss.tx_path import KISSDataRequestReceipt
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.service.classic_console import ProductClassicConsoleConfig
from ywd1278.service.classic_tx_console import (
    ProductClassicTXConfigurationError,
    ProductClassicTXConfig,
    ProductClassicTXConsole,
    load_product_classic_tx_config,
    make_product_backend_submitter,
)


class FakeBackend:
    def __init__(self, result) -> None:  # type: ignore[no-untyped-def]
        self.result = result
        self.messages: list[KISSMessage] = []

    def reject_client_message(self, message: KISSMessage):  # type: ignore[no-untyped-def]
        self.messages.append(message)
        return self.result


def receipt(request_id: int = 7) -> KISSDataRequestReceipt:
    return KISSDataRequestReceipt(
        request_id=request_id,
        frame_bytes_no_fcs=22,
        frame_bytes_with_fcs=24,
        parameter_generation=3,
        txdelay=30,
        persist=63,
        slottime=10,
        enqueued_at=1.0,
        deadline_at=31.0,
    )


class ProductClassicTX0FTests(unittest.TestCase):
    def test_missing_station_preserves_historical_p5_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            path.write_text("[packet]\npaclen=128\n", encoding="utf-8")
            config = load_product_classic_tx_config(path)
            self.assertFalse(config.configured)
            self.assertIsNone(config.source)
            self.assertEqual(config.paclen, 128)

            console = ProductClassicTXConsole(
                ProductClassicConsoleConfig(enabled=False),
                tx_config=config,
                tx_enabled=False,
                tx_submitter=lambda frame: None,  # type: ignore[arg-type,return-value]
                diagnostics_snapshot=DiagnosticsStatus().snapshot,
                mheard_db=None,
            )
            created = console._shell_factory()
            self.assertIsInstance(created, ClassicTNCCommandShell)
            self.assertNotIsInstance(created, ClassicTXCommandShell)
            self.assertIn("OWNER=0F", created.execute("UNPROTO CQ").lines[0])

    def test_station_and_paclen_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            path.write_text(
                "[station]\ncallsign=\"KJ6YWD\"\nssid=10\n"
                "[packet]\npaclen=200\n",
                encoding="utf-8",
            )
            config = load_product_classic_tx_config(path)
            self.assertTrue(config.configured)
            self.assertEqual(str(config.source), "KJ6YWD-10")
            self.assertEqual(config.paclen, 200)

        invalid = (
            ("[station]\ncallsign=\"\"\nssid=0\n", "callsign"),
            ("[station]\ncallsign=\"KJ6YWD\"\nssid=16\n", "ssid"),
            ("[station]\ncallsign=\"KJ6YWD\"\nssid=0\n[packet]\npaclen=0\n", "paclen"),
            ("[station]\ncallsign=\"TOOLONG7\"\nssid=0\n", "station identity"),
        )
        for payload, marker in invalid:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "config.toml"
                path.write_text(payload, encoding="utf-8")
                with self.assertRaisesRegex(ProductClassicTXConfigurationError, marker):
                    load_product_classic_tx_config(path)

    def test_backend_adapter_sends_one_port_zero_kiss_data_message(self) -> None:
        backend = FakeBackend(KISSDataIngressResult(True, receipt(9), "accepted"))
        submit = make_product_backend_submitter(lambda: backend)
        frame = b"test-frame-body"
        result = submit(frame)
        self.assertTrue(result.admitted)
        self.assertEqual(result.request_id, 9)
        self.assertEqual(len(backend.messages), 1)
        message = backend.messages[0]
        self.assertEqual(message.port, 0)
        self.assertEqual(message.command, DATA)
        self.assertEqual(message.frame, frame)

    def test_backend_adapter_maps_fail_closed_results_without_retry(self) -> None:
        backend = FakeBackend(SimpleNamespace(reason="TX disabled"))
        submit = make_product_backend_submitter(lambda: backend)
        result = submit(b"frame")
        self.assertFalse(result.admitted)
        self.assertIsNone(result.request_id)
        self.assertIn("TX disabled", result.reason)
        self.assertEqual(len(backend.messages), 1)

        unavailable = make_product_backend_submitter(lambda: None)
        result = unavailable(b"frame")
        self.assertFalse(result.admitted)
        self.assertIn("unavailable", result.reason)

    def test_configured_console_creates_fresh_0f_session_with_tx_policy(self) -> None:
        backend = FakeBackend(KISSDataIngressResult(True, receipt(1), "accepted"))
        console = ProductClassicTXConsole(
            ProductClassicConsoleConfig(enabled=False),
            tx_config=ProductClassicTXConfig(
                source=Address.parse("KJ6YWD-10"),
                paclen=128,
            ),
            tx_enabled=True,
            tx_submitter=make_product_backend_submitter(lambda: backend),
            diagnostics_snapshot=DiagnosticsStatus().snapshot,
            mheard_db=None,
        )
        first = console._shell_factory()
        second = console._shell_factory()
        self.assertIsInstance(first, ClassicTXCommandShell)
        self.assertIsInstance(second, ClassicTXCommandShell)
        self.assertIsNot(first, second)
        first.execute("UNPROTO YWD127")
        self.assertEqual(first.tx_snapshot.destination, "YWD127")
        self.assertIsNone(second.tx_snapshot.destination)

    def test_tx_enabled_requires_station_identity(self) -> None:
        with self.assertRaisesRegex(ProductClassicTXConfigurationError, "station"):
            ProductClassicTXConsole(
                ProductClassicConsoleConfig(enabled=False),
                tx_config=ProductClassicTXConfig(source=None),
                tx_enabled=True,
                tx_submitter=make_product_backend_submitter(lambda: None),
                diagnostics_snapshot=DiagnosticsStatus().snapshot,
                mheard_db=None,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
