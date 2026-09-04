#!/usr/bin/env python3
"""Regression tests for 0E-P3 authenticated private-LAN console."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from ywd1278.console.auth import (
    CredentialRecord,
    hash_password,
    load_credential_file,
    parse_credential,
    verify_password,
    write_credential_file,
)
from ywd1278.console.lan_telnet import (
    AuthenticatedLanTNCServer,
    validate_client_address,
    validate_lan_bind,
)
from ywd1278.console.local import LocalTNCCommandShell


TEST_USERNAME = "ywd"
TEST_PASSWORD = "correct-horse-1278"
TEST_SALT = bytes(range(16))


def test_credential() -> CredentialRecord:
    return CredentialRecord(
        username=TEST_USERNAME,
        password_hash=hash_password(
            TEST_PASSWORD,
            salt=TEST_SALT,
            iterations=200_000,
        ),
    )


def recv_until(sock: socket.socket, marker: bytes, timeout: float = 3.0) -> bytes:
    data = bytearray()
    sock.settimeout(timeout)
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class CredentialTests(unittest.TestCase):
    def test_hash_is_salted_bounded_and_verifies(self) -> None:
        record = test_credential()
        self.assertTrue(record.password_hash.startswith("pbkdf2-sha256$200000$"))
        self.assertTrue(verify_password(TEST_PASSWORD, record.password_hash))
        self.assertFalse(verify_password("wrong-password-1278", record.password_hash))
        second = hash_password(
            TEST_PASSWORD,
            salt=b"Z" * 16,
            iterations=200_000,
        )
        self.assertNotEqual(record.password_hash, second)

    def test_credential_parser_fails_closed(self) -> None:
        record = test_credential()
        parsed = parse_credential(f"{record.username}:{record.password_hash}\n")
        self.assertEqual(parsed, record)
        bad_values = (
            "",
            "ywd",
            "bad user:pbkdf2-sha256$200000$a$b\n",
            "ywd:plaintext\n",
            "ywd:pbkdf2-sha256$1$a$b\n",
            f"{record.username}:{record.password_hash}\nextra:x\n",
        )
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    parse_credential(value)

    def test_auth_file_requires_private_permissions_and_rejects_symlink(self) -> None:
        record = test_credential()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "console.auth"
            write_credential_file(path, record)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(load_credential_file(path), record)

            os.chmod(path, 0o644)
            with self.assertRaisesRegex(ValueError, "group/world"):
                load_credential_file(path)

            os.chmod(path, 0o600)
            link = Path(tmp) / "console-link.auth"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                load_credential_file(link)


class AddressPolicyTests(unittest.TestCase):
    def test_bind_accepts_only_loopback_or_rfc1918_literal_ipv4(self) -> None:
        accepted = (
            "127.0.0.1",
            "127.20.30.40",
            "10.0.0.1",
            "10.255.255.254",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.165",
        )
        for address in accepted:
            with self.subTest(address=address):
                self.assertEqual(validate_lan_bind(address), address)

        rejected = (
            "0.0.0.0",
            "8.8.8.8",
            "100.64.0.1",
            "169.254.1.1",
            "172.15.255.255",
            "172.32.0.1",
            "192.0.2.1",
            "localhost",
            "::1",
            "",
        )
        for address in rejected:
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    validate_lan_bind(address)

    def test_client_source_policy_matches_private_scope(self) -> None:
        for address in ("127.0.0.1", "10.2.3.4", "172.20.1.2", "192.168.50.10"):
            self.assertTrue(validate_client_address(address), address)
        for address in ("0.0.0.0", "8.8.8.8", "100.64.0.1", "169.254.1.1", "::1"):
            self.assertFalse(validate_client_address(address), address)


class AuthenticatedServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell_creations = 0

        def shell_factory() -> LocalTNCCommandShell:
            self.shell_creations += 1
            return LocalTNCCommandShell()

        self.server = AuthenticatedLanTNCServer(
            ("127.0.0.1", 0),
            credential=test_credential(),
            shell_factory=shell_factory,
            auth_timeout_seconds=2.0,
            idle_timeout_seconds=2.0,
            max_session_seconds=10.0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3.0)

    def connect(self) -> socket.socket:
        deadline = time.monotonic() + 2.0
        while True:
            try:
                return socket.create_connection((self.host, self.port), timeout=1.0)
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

    def authenticate(self, sock: socket.socket, password: str = TEST_PASSWORD) -> bytes:
        banner = recv_until(sock, b"Username:")
        self.assertIn(b"AUTHENTICATED LAN TNC CONSOLE", banner)
        self.assertIn(b"NOT encrypted", banner)
        sock.sendall(TEST_USERNAME.encode("ascii") + b"\r\n")
        password_prompt = recv_until(sock, b"Password:")
        self.assertIn(b"Password:", password_prompt)
        sock.sendall(password.encode("ascii") + b"\r\n")
        return recv_until(sock, b"cmd:" if password == TEST_PASSWORD else b"Username:")

    def command(self, sock: socket.socket, text: str, marker: bytes = b"cmd:") -> str:
        sock.sendall(text.encode("ascii") + b"\r\n")
        return recv_until(sock, marker).decode("ascii", "replace")

    def test_failed_auth_does_not_construct_or_reach_p1_shell(self) -> None:
        sock = self.connect()
        failed = self.authenticate(sock, "wrong-password-1278")
        self.assertIn(b"AUTH FAIL 1/3", failed)
        self.assertEqual(self.shell_creations, 0)
        sock.close()

    def test_auth_timeout_closes_without_shell_creation(self) -> None:
        self.server.auth_timeout_seconds = 0.15
        sock = self.connect()
        recv_until(sock, b"Username:")
        timed_out = recv_until(sock, b"BYE\r\n", timeout=1.0)
        self.assertIn(b"ERROR AUTH timeout", timed_out)
        self.assertIn(b"BYE", timed_out)
        self.assertEqual(self.shell_creations, 0)
        sock.close()

    def test_live_authenticated_session_reuses_p1_and_rejects_future_tx_commands(self) -> None:
        sock = self.connect()
        authenticated = self.authenticate(sock)
        self.assertIn(b"AUTH OK", authenticated)
        self.assertIn(b"YWD-1278 0.1.0-alpha0", authenticated)
        self.assertEqual(self.shell_creations, 1)

        self.assertIn("YWD-1278 0.1.0-alpha0", self.command(sock, "VERSION"))
        self.assertIn("MCOM OFF", self.command(sock, "MCOM"))
        updated = self.command(sock, "MCOM ON")
        self.assertIn("MCOM ON", updated)
        self.assertIn("MONITOR_GENERATION 1", updated)
        self.assertIn("ERROR UNKNOWN COMMAND CONNECT", self.command(sock, "CONNECT KJ6YWD"))
        self.assertIn("ERROR UNKNOWN COMMAND TX", self.command(sock, "TX hello"))
        bye = self.command(sock, "QUIT", marker=b"BYE\r\n")
        self.assertIn("BYE", bye)
        sock.close()

    def test_reconnect_requires_auth_again_and_resets_monitor_policy(self) -> None:
        first = self.connect()
        self.authenticate(first)
        self.assertIn("MCOM ON", self.command(first, "MCOM ON"))
        self.command(first, "QUIT", marker=b"BYE\r\n")
        first.close()

        second = self.connect()
        preauth = recv_until(second, b"Username:")
        self.assertIn(b"Username:", preauth)
        self.assertNotIn(b"cmd:", preauth)
        self.assertEqual(self.shell_creations, 1)
        second.sendall(TEST_USERNAME.encode("ascii") + b"\r\n")
        recv_until(second, b"Password:")
        second.sendall(TEST_PASSWORD.encode("ascii") + b"\r\n")
        recv_until(second, b"cmd:")
        self.assertEqual(self.shell_creations, 2)
        self.assertIn("MCOM OFF", self.command(second, "MCOM"))
        self.command(second, "QUIT", marker=b"BYE\r\n")
        second.close()

    def test_auth_attempt_limit_closes_without_shell_creation(self) -> None:
        sock = self.connect()
        recv_until(sock, b"Username:")
        for attempt in range(1, 4):
            sock.sendall(TEST_USERNAME.encode("ascii") + b"\r\n")
            recv_until(sock, b"Password:")
            sock.sendall(b"wrong-password-1278\r\n")
            marker = b"BYE\r\n" if attempt == 3 else b"Username:"
            data = recv_until(sock, marker)
            self.assertIn(f"AUTH FAIL {attempt}/3".encode("ascii"), data)
        self.assertIn(b"ERROR AUTH attempt limit reached", data)
        self.assertIn(b"BYE", data)
        self.assertEqual(self.shell_creations, 0)
        sock.close()

    def test_client_limit_rejects_second_unauthenticated_connection(self) -> None:
        creations = 0

        def factory() -> LocalTNCCommandShell:
            nonlocal creations
            creations += 1
            return LocalTNCCommandShell()

        limited = AuthenticatedLanTNCServer(
            ("127.0.0.1", 0),
            credential=test_credential(),
            shell_factory=factory,
            max_clients=1,
            auth_timeout_seconds=2.0,
            idle_timeout_seconds=2.0,
            max_session_seconds=10.0,
        )
        thread = threading.Thread(target=limited.serve_forever, daemon=True)
        thread.start()
        first = second = None
        try:
            host, port = limited.server_address
            first = socket.create_connection((host, port), timeout=1.0)
            recv_until(first, b"Username:")
            second = socket.create_connection((host, port), timeout=1.0)
            rejected = recv_until(second, b"\r\n")
            self.assertIn(b"BUSY maximum Telnet clients reached", rejected)
            self.assertEqual(creations, 0)
        finally:
            if first is not None:
                first.close()
            if second is not None:
                second.close()
            limited.shutdown()
            limited.server_close()
            thread.join(timeout=3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
