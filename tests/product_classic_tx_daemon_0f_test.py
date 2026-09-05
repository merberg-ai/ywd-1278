#!/usr/bin/env python3
"""0F P3 full-daemon host qualification over the qualified fake HAT."""

from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from product_classic_console_stage_d_test import connect_when_ready, read_socket_until
from product_daemon_stage_b_test import StageBTransport, config_text, free_port, wait_until
from ywd1278.daemon import run_daemon


def write_0f_config(
    directory: str,
    *,
    tx_enabled: bool,
    tx_power: int,
    console_port: int,
) -> Path:
    base = config_text(
        port=free_port(),
        tx_enabled=tx_enabled,
        tx_power=tx_power,
        persist=255,
        kiss_enabled=False,
    )
    base = base.replace(
        "slottime_ms = 100\n",
        "slottime_ms = 100\npaclen = 128\n",
        1,
    )
    text = (
        "[station]\ncallsign = \"KJ6YWD\"\nssid = 10\n\n"
        + base
        + f'''\n[console]\nenabled = true\nlisten = "127.0.0.1"\nport = {console_port}\npty_enabled = false\n'''
    )
    path = Path(directory) / "0f.toml"
    path.write_text(text, encoding="utf-8")
    return path


def run_with_fake(path: Path):  # type: ignore[no-untyped-def]
    created: list[StageBTransport] = []

    def factory() -> StageBTransport:
        transport = StageBTransport()
        created.append(transport)
        return transport

    stop = threading.Event()
    result: list[int] = []
    errors: list[BaseException] = []

    def target() -> None:
        try:
            result.append(
                run_daemon(
                    path,
                    stop_event=stop,
                    transport_factory=factory,
                    random_byte_source=lambda: 0,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target, name="0f-product-daemon")
    thread.start()
    wait_until(lambda: bool(created) and created[0].rx_active, detail="0F daemon RX")
    return created, stop, result, errors, thread


class ProductClassicTXDaemon0FTests(unittest.TestCase):
    def test_tx_disabled_station_console_fails_closed_before_product_admission(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            console_port = free_port()
            path = write_0f_config(
                td,
                tx_enabled=False,
                tx_power=64,
                console_port=console_port,
            )
            created, stop, result, errors, thread = run_with_fake(path)
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", console_port)
                banner = read_socket_until(client, b"cmd:")
                self.assertIn(b"TELNET TNC CONSOLE", banner)

                client.sendall(b"UNPROTO YWD127\r")
                self.assertIn(
                    b"UNPROTO DEST=YWD127 VIA=DIRECT",
                    read_socket_until(client, b"cmd:"),
                )
                client.sendall(b"CONVERSE\r")
                reply = read_socket_until(client, b"cmd:")
                self.assertIn(b"ERROR CONVERSE TX DISABLED", reply)

                self.assertEqual(created[0].tx_accept_count, 0)
                self.assertEqual(created[0].rx_stop_count, 0)
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [0])
            self.assertEqual(created[0].tx_accept_count, 0)
            self.assertEqual(created[0].rx_start_count, 1)
            self.assertEqual(created[0].rx_stop_count, 1)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)

    def test_one_converse_line_traverses_existing_csma_half_duplex_graph_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            console_port = free_port()
            path = write_0f_config(
                td,
                tx_enabled=True,
                tx_power=200,
                console_port=console_port,
            )
            created, stop, result, errors, thread = run_with_fake(path)
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", console_port)
                read_socket_until(client, b"cmd:")

                client.sendall(b"UNPROTO YWD127 VIA WIDE1-1\r")
                reply = read_socket_until(client, b"cmd:")
                self.assertIn(b"UNPROTO DEST=YWD127 VIA=WIDE1-1", reply)

                client.sendall(b"CONVERSE\r")
                reply = read_socket_until(client, b"cmd:")
                self.assertIn(b"CONVERSE MODE DEST=YWD127 VIA=WIDE1-1", reply)

                client.sendall(b"0F HOST GRAPH ONE\r")
                reply = read_socket_until(client, b"cmd:")
                self.assertIn(b"TX QUEUED REQUEST=1", reply)
                self.assertIn(b"INFO_BYTES=17", reply)

                wait_until(
                    lambda: created[0].tx_accept_count == 1,
                    timeout=6.0,
                    detail="0F fake-HAT TX",
                )
                self.assertEqual(created[0].tx_accept_count, 1)
                self.assertEqual(created[0].rx_stop_count, 1)
                self.assertEqual(created[0].rx_start_count, 2)

                client.sendall(b"COMMAND\r")
                self.assertIn(b"COMMAND MODE", read_socket_until(client, b"cmd:"))
                client.sendall(b"VER\r")
                self.assertIn(b"YWD-1278 0.1.0-alpha0", read_socket_until(client, b"cmd:"))

                # Hold after command-mode return; no background retry or second
                # console dispatch may appear.
                time.sleep(0.25)
                self.assertEqual(created[0].tx_accept_count, 1)
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [0])
            self.assertEqual(created[0].tx_accept_count, 1)
            self.assertEqual(created[0].rx_stop_count, 2)  # one TX + final daemon stop
            self.assertEqual(created[0].rx_start_count, 2)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
            self.assertTrue(
                all(tid == created[0].owner_thread_id for tid in created[0].call_thread_ids)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
