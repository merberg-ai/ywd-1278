#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import select
import socket
import tempfile
import threading
import time
import unittest

from product_daemon_stage_b_test import StageBTransport, body, rx_capture, wait_until
from product_observability_stage_c_test import stage_c_config_text
from ywd1278.console.auth import CredentialRecord, hash_password, write_credential_file
from ywd1278.console.lan_telnet import AuthenticatedLanTNCServer
from ywd1278.daemon import run_daemon
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.service.classic_console import (
    ProductClassicConsole,
    ProductClassicConsoleConfigurationError,
    ProductClassicConsoleConfig,
    load_product_classic_console_config,
)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_socket_until(sock: socket.socket, needle: bytes, *, timeout: float = 3.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timeout waiting for {needle!r}: {bytes(data)!r}")
        sock.settimeout(remaining)
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError(f"socket closed waiting for {needle!r}: {bytes(data)!r}")
        data.extend(chunk)
    return bytes(data)


def read_fd_until(fd: int, needle: bytes, *, timeout: float = 3.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timeout waiting for {needle!r}: {bytes(data)!r}")
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(fd, 4096)
        if chunk:
            data.extend(chunk)
    return bytes(data)


def connect_when_ready(host: str, port: int, *, timeout: float = 5.0) -> socket.socket:
    deadline = time.monotonic() + timeout
    error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            return socket.create_connection((host, port), timeout=0.5)
        except OSError as exc:
            error = exc
            time.sleep(0.02)
    raise AssertionError(f"console listener did not become ready: {error}")


def write_stage_d_config(
    directory: str,
    *,
    database: Path,
    console_port: int,
    pty_link: Path,
) -> Path:
    path = Path(directory) / "stage-d.toml"
    text = stage_c_config_text(
        database=database,
        monitor_enabled=True,
        log_frames=True,
        kiss_enabled=True,
    )
    text += f'''\n[console]\nenabled = true\nlisten = "127.0.0.1"\nport = {console_port}\npty_enabled = true\npty_link = "{pty_link}"\n'''
    path.write_text(text, encoding="utf-8")
    return path


class StageDClassicConsoleTests(unittest.TestCase):
    def test_console_configuration_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            empty = root / "empty.toml"
            empty.write_text("", encoding="utf-8")
            self.assertFalse(load_product_classic_console_config(empty).enabled)

            good = root / "good.toml"
            good.write_text(
                f'''[console]\nenabled = true\nlisten = "127.0.0.1"\nport = 8010\npty_enabled = true\npty_link = "{root / 'tnc'}"\n''',
                encoding="utf-8",
            )
            config = load_product_classic_console_config(good)
            self.assertTrue(config.enabled)
            self.assertEqual(config.host, "127.0.0.1")
            self.assertTrue(config.pty_enabled)
            self.assertEqual(config.pty_link, root / "tnc")

            cases = [
                (
                    "public.toml",
                    '[console]\nenabled=true\nlisten="8.8.8.8"\nport=8010\n',
                    "loopback or RFC1918",
                ),
                (
                    "rfc1918-no-auth.toml",
                    '[console]\nenabled=true\nlisten="192.168.1.10"\nport=8010\n',
                    "requires console.auth_file",
                ),
                (
                    "relative-auth.toml",
                    '[console]\nenabled=true\nlisten="127.0.0.1"\nport=8010\nauth_file="auth.txt"\n',
                    "auth_file must be an absolute path",
                ),
                (
                    "relative-pty.toml",
                    '[console]\nenabled=true\nlisten="127.0.0.1"\nport=8010\npty_enabled=true\npty_link="tnc"\n',
                    "pty_link must be an absolute path",
                ),
                (
                    "link-without-pty.toml",
                    f'[console]\nenabled=true\nlisten="127.0.0.1"\nport=8010\npty_link="{root / "tnc2"}"\n',
                    "pty_link requires console.pty_enabled=true",
                ),
            ]
            for filename, payload, message in cases:
                with self.subTest(filename=filename):
                    candidate = root / filename
                    candidate.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(ProductClassicConsoleConfigurationError, message):
                        load_product_classic_console_config(candidate)

            rfc1918 = root / "rfc1918-auth.toml"
            rfc1918.write_text(
                f'[console]\nenabled=true\nlisten="192.168.1.10"\nport=8010\nauth_file="{root / "auth"}"\n',
                encoding="utf-8",
            )
            accepted = load_product_classic_console_config(rfc1918)
            self.assertEqual(accepted.host, "192.168.1.10")
            self.assertEqual(accepted.auth_file, root / "auth")

    def test_authenticated_p3_is_selected_when_auth_file_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            auth_file = root / "console.auth"
            password = "stage-d-password"
            record = CredentialRecord(
                username="kj6ywd",
                password_hash=hash_password(password, salt=b"D" * 16),
            )
            write_credential_file(auth_file, record)

            diagnostics = DiagnosticsStatus()
            console = ProductClassicConsole(
                ProductClassicConsoleConfig(
                    enabled=True,
                    host="127.0.0.1",
                    port=free_port(),
                    auth_file=auth_file,
                    pty_enabled=False,
                ),
                diagnostics_snapshot=diagnostics.snapshot,
                mheard_db=None,
            )
            console.start()
            try:
                self.assertIsInstance(console.telnet_server, AuthenticatedLanTNCServer)
                snapshot = console.snapshot
                self.assertTrue(snapshot.running)
                self.assertTrue(snapshot.telnet_authenticated)
                assert snapshot.telnet_listener is not None
                with socket.create_connection(snapshot.telnet_listener, timeout=2.0) as client:
                    before_auth = read_socket_until(client, b"Username:")
                    self.assertIn(b"AUTHENTICATED LAN TNC CONSOLE", before_auth)
                    self.assertNotIn(b"cmd:", before_auth)
                    client.sendall(b"kj6ywd\r")
                    read_socket_until(client, b"Password:")
                    client.sendall(password.encode("ascii") + b"\r")
                    authenticated = read_socket_until(client, b"cmd:")
                    self.assertIn(b"AUTH OK", authenticated)
                    client.sendall(b"CONNECT KJ6YWD\r")
                    reply = read_socket_until(client, b"cmd:")
                    self.assertIn(
                        b"ERROR CONNECT NOT AVAILABLE IN 0E-P5; OWNER=0G",
                        reply,
                    )
            finally:
                console.stop()

    def test_full_daemon_exposes_live_telnet_pty_mheard_status_and_no_tx(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "frames.sqlite3"
            pty_link = root / "tnc"
            console_port = free_port()
            config_path = write_stage_d_config(
                td,
                database=database,
                console_port=console_port,
                pty_link=pty_link,
            )
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

            thread = threading.Thread(target=target, name="stage-d-full-daemon")
            thread.start()
            telnet: socket.socket | None = None
            pty_fd: int | None = None
            try:
                wait_until(
                    lambda: bool(created) and created[0].rx_active,
                    timeout=5.0,
                    detail="Stage-D daemon RX",
                )
                telnet = connect_when_ready("127.0.0.1", console_port)
                banner = read_socket_until(telnet, b"cmd:")
                self.assertIn(b"TELNET TNC CONSOLE", banner)

                wait_until(
                    lambda: pty_link.is_symlink(),
                    timeout=5.0,
                    detail="Stage-D stable PTY link",
                )
                self.assertTrue(str(pty_link.resolve()).startswith("/dev/pts/"))
                pty_fd = os.open(
                    pty_link,
                    os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK,
                )
                pty_banner = read_fd_until(pty_fd, b"cmd:")
                self.assertIn(b"VIRTUAL PTY TNC CONSOLE", pty_banner)

                inbound = body("STAGE D LIVE CONSOLE")
                created[0].inject_rx_packed(rx_capture(inbound))
                mheard = MHeardDatabase(database)

                def persisted() -> bool:
                    try:
                        return mheard.summary().frame_count >= 1
                    except Exception:
                        return False

                wait_until(persisted, timeout=5.0, detail="Stage-D persisted MHEARD")

                telnet.sendall(b"MH\r")
                reply = read_socket_until(telnet, b"cmd:")
                self.assertIn(b"MHEARD 1", reply)
                self.assertIn(b"KJ6YWD-10", reply)

                telnet.sendall(b"STAT\r")
                reply = read_socket_until(telnet, b"cmd:")
                self.assertIn(b"STATUS OK", reply)
                self.assertIn(b"PROBLEMS NONE", reply)

                telnet.sendall(b"MCOM ON\r")
                self.assertIn(b"MCOM ON", read_socket_until(telnet, b"cmd:"))
                telnet.sendall(b"DISP\r")
                self.assertIn(b"MCOM ON", read_socket_until(telnet, b"cmd:"))

                telnet.sendall(b"UNPROTO CQ\r")
                self.assertIn(
                    b"ERROR UNPROTO NOT AVAILABLE IN 0E-P5; OWNER=0F",
                    read_socket_until(telnet, b"cmd:"),
                )
                telnet.sendall(b"TX hello\r")
                self.assertIn(
                    b"ERROR TX NOT AVAILABLE IN 0E-P5; OWNER=LATER-TX-COMMAND",
                    read_socket_until(telnet, b"cmd:"),
                )

                os.write(pty_fd, b"MH\r")
                pty_reply = read_fd_until(pty_fd, b"cmd:")
                self.assertIn(b"MHEARD 1", pty_reply)
                self.assertIn(b"KJ6YWD-10", pty_reply)
                os.write(pty_fd, b"HEAL\r")
                self.assertIn(b"HEALTH OK", read_fd_until(pty_fd, b"cmd:"))
                os.write(pty_fd, b"CONNECT KJ6YWD\r")
                self.assertIn(
                    b"ERROR CONNECT NOT AVAILABLE IN 0E-P5; OWNER=0G",
                    read_fd_until(pty_fd, b"cmd:"),
                )

                # A second Telnet connection must receive fresh per-session
                # monitor policy rather than inheriting MCOM from the first.
                with connect_when_ready("127.0.0.1", console_port) as second:
                    read_socket_until(second, b"cmd:")
                    second.sendall(b"DISP\r")
                    fresh = read_socket_until(second, b"cmd:")
                    self.assertIn(b"MCOM OFF", fresh)

                self.assertEqual(created[0].tx_accept_count, 0)
            finally:
                if pty_fd is not None:
                    os.close(pty_fd)
                if telnet is not None:
                    telnet.close()
                stop_event.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [0])
            self.assertFalse(pty_link.exists())
            self.assertFalse(pty_link.is_symlink())
            self.assertEqual(created[0].tx_accept_count, 0)
            self.assertEqual(created[0].rx_start_count, 1)
            self.assertEqual(created[0].rx_stop_count, 1)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
            self.assertTrue(
                all(tid == created[0].owner_thread_id for tid in created[0].call_thread_ids)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
