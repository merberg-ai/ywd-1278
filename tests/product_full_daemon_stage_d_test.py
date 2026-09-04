#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import tomllib
import unittest

from product_classic_console_stage_d_test import (
    connect_when_ready,
    read_socket_until,
    write_stage_d_config,
)
from product_daemon_stage_b_test import (
    StageBTransport,
    body,
    recv_data,
    rx_capture,
    wait_until,
)
from ywd1278.daemon import run_daemon
from ywd1278.monitor.mheard import MHeardDatabase


class StageDFullDaemonGraphTests(unittest.TestCase):
    def test_one_rx_is_simultaneously_visible_to_kiss_and_classic_console(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "frames.sqlite3"
            pty_link = root / "tnc"
            console_port = 0
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", 0))
                console_port = int(probe.getsockname()[1])

            config_path = write_stage_d_config(
                td,
                database=database,
                console_port=console_port,
                pty_link=pty_link,
            )
            with config_path.open("rb") as handle:
                root_config = tomllib.load(handle)
            kiss_port = int(root_config["kiss"]["port"])

            stop_event = threading.Event()
            result: list[int] = []
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    result.append(
                        run_daemon(
                            config_path,
                            stop_event=stop_event,
                            transport_factory=factory,
                            random_byte_source=lambda: 0,
                        )
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=target, name="stage-d-simultaneous-full-graph")
            thread.start()
            telnet: socket.socket | None = None
            kiss: socket.socket | None = None
            try:
                wait_until(
                    lambda: bool(created) and created[0].rx_active,
                    timeout=5.0,
                    detail="Stage-D full graph RX",
                )
                telnet = connect_when_ready("127.0.0.1", console_port)
                read_socket_until(telnet, b"cmd:")
                kiss = connect_when_ready("127.0.0.1", kiss_port)
                wait_until(
                    lambda: pty_link.is_symlink(),
                    timeout=5.0,
                    detail="Stage-D full graph PTY",
                )

                inbound = body("STAGE D SAME PACKET FULL GRAPH")
                created[0].inject_rx_packed(rx_capture(inbound))
                message = recv_data(kiss, timeout=4.0)
                self.assertEqual(message.frame, inbound)

                mheard = MHeardDatabase(database)

                def persisted() -> bool:
                    try:
                        return mheard.summary().frame_count >= 1
                    except Exception:
                        return False

                wait_until(persisted, timeout=5.0, detail="Stage-D full graph MHEARD")
                telnet.sendall(b"MH\r")
                reply = read_socket_until(telnet, b"cmd:")
                self.assertIn(b"MHEARD 1", reply)
                self.assertIn(b"KJ6YWD-10", reply)
                telnet.sendall(b"HEAL\r")
                self.assertIn(b"HEALTH OK", read_socket_until(telnet, b"cmd:"))

                self.assertEqual(created[0].tx_accept_count, 0)
            finally:
                if kiss is not None:
                    kiss.close()
                if telnet is not None:
                    telnet.close()
                stop_event.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [0])
            self.assertFalse(pty_link.is_symlink())
            self.assertEqual(created[0].tx_accept_count, 0)
            self.assertEqual(created[0].rx_start_count, 1)
            self.assertEqual(created[0].rx_stop_count, 1)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
