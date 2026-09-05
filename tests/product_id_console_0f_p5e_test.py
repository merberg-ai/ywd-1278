#!/usr/bin/env python3
"""Host behavior tests for the 0F-P5e manual ID command."""

from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from product_classic_console_stage_d_test import connect_when_ready, read_socket_until
from product_classic_tx_daemon_0f_test import write_0f_config
from product_daemon_stage_b_test import StageBTransport, free_port, wait_until
from ywd1278.ax25 import Address, parse_ui_frame
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.daemon import run_daemon
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.service.classic_console import ProductClassicConsoleConfig
from ywd1278.service.classic_tx_console import ProductClassicTXConfig
from ywd1278.service.product_beacon_console import ThreadSafeProductBeaconCoordinator
from ywd1278.service.product_id_console import ProductClassicIDConsole, ProductIDCommandShell


class Capture:
    def __init__(self, *, admitted: bool = True) -> None:
        self.frames: list[bytes] = []
        self.admitted = admitted

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        self.frames.append(bytes(frame))
        return ClassicTXSubmitResult(
            self.admitted,
            len(self.frames) if self.admitted else None,
            "accepted" if self.admitted else "queue full",
        )


def shell(*, enabled: bool, capture: Capture, paclen: int = 128) -> ProductIDCommandShell:
    beacon = ThreadSafeProductBeaconCoordinator(
        source=Address.parse("KJ6YWD-10"), paclen=paclen,
        tx_enabled=enabled, tx_submitter=capture,
    )
    console = ProductClassicIDConsole(
        ProductClassicConsoleConfig(enabled=False),
        tx_config=ProductClassicTXConfig(source=Address.parse("KJ6YWD-10"), paclen=paclen),
        tx_enabled=enabled,
        tx_submitter=capture,
        beacon=beacon,
        diagnostics_snapshot=DiagnosticsStatus().snapshot,
        mheard_db=None,
    )
    created = console._shell_factory()
    assert isinstance(created, ProductIDCommandShell)
    return created


class ProductIDConsoleP5eTests(unittest.TestCase):
    def test_id_is_fixed_direct_ui_frame_with_no_fcs(self) -> None:
        capture = Capture()
        tnc = shell(enabled=True, capture=capture)
        result = tnc.execute("ID")
        self.assertEqual(result.lines, ("ID QUEUED REQUEST=1 DEST=ID VIA=DIRECT INFO_BYTES=21",))
        self.assertEqual(len(capture.frames), 1)
        parsed = parse_ui_frame(capture.frames[0], has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), "ID")
        self.assertEqual(tuple(parsed["path"]), ())
        self.assertEqual(parsed["info"], b"YWD-1278 ID KJ6YWD-10")
        self.assertEqual(tnc.id_snapshot.attempts, 1)
        self.assertEqual(tnc.id_snapshot.accepted, 1)

    def test_id_fails_closed_when_tx_disabled_or_paclen_too_small(self) -> None:
        capture = Capture()
        disabled = shell(enabled=False, capture=capture)
        self.assertIn("TX DISABLED", disabled.execute("ID").lines[0])
        self.assertEqual(capture.frames, [])

        short = shell(enabled=True, capture=capture, paclen=10)
        self.assertIn("exceeds PACLEN", short.execute("ID").lines[0])
        self.assertEqual(capture.frames, [])

    def test_rejection_is_one_attempt_without_retry(self) -> None:
        capture = Capture(admitted=False)
        tnc = shell(enabled=True, capture=capture)
        self.assertEqual(tnc.execute("ID").lines, ("ERROR ID REJECTED queue full",))
        self.assertEqual(len(capture.frames), 1)
        time.sleep(0.05)
        self.assertEqual(len(capture.frames), 1)
        self.assertEqual(tnc.id_snapshot.attempts, 1)
        self.assertEqual(tnc.id_snapshot.accepted, 0)

    def test_id_does_not_modify_unproto_beacon_or_converse_state(self) -> None:
        capture = Capture()
        tnc = shell(enabled=True, capture=capture)
        tnc.execute("BTEXT beacon state")
        tnc.execute("UNPROTO BEACON VIA WIDE1-1")
        tnc.execute("BEACON EVERY 10")
        before = tnc.tx_snapshot
        tnc.execute("ID")
        after = tnc.tx_snapshot
        self.assertEqual(before.destination, after.destination)
        self.assertEqual(before.path, after.path)
        self.assertFalse(after.converse_mode)
        self.assertIn("BEACON EVERY 10", tnc.execute("BEACON").lines[0])
        tnc.execute("BEACON OFF")

    def test_full_daemon_id_traverses_existing_fake_hat_graph_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            port = free_port()
            path = write_0f_config(td, tx_enabled=True, tx_power=200, console_port=port)
            created: list[StageBTransport] = []

            def factory() -> StageBTransport:
                transport = StageBTransport()
                created.append(transport)
                return transport

            stop = threading.Event()
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    run_daemon(
                        path, stop_event=stop, transport_factory=factory,
                        random_byte_source=lambda: 0,
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=target, name="p5e-id-daemon")
            thread.start()
            wait_until(lambda: bool(created) and created[0].rx_active, detail="P5e daemon RX")
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", port)
                read_socket_until(client, b"cmd:")
                client.sendall(b"ID\r")
                self.assertIn(b"ID QUEUED REQUEST=1 DEST=ID", read_socket_until(client, b"cmd:"))
                wait_until(
                    lambda: created[0].tx_accept_count == 1 and created[0].rx_active,
                    timeout=6.0,
                    detail="P5e one fake-HAT ID and RX recovery",
                )
                time.sleep(0.15)
                self.assertEqual(created[0].tx_accept_count, 1)
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(created[0].tx_accept_count, 1)
            self.assertEqual(created[0].rx_start_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
