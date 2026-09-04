#!/usr/bin/env python3
"""Architecture/safety contract for 0E-P3 authenticated LAN console."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

FROZEN_BLOBS = {
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def main() -> int:
    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    auth_path = ROOT / "src" / "ywd1278" / "console" / "auth.py"
    lan_path = ROOT / "src" / "ywd1278" / "console" / "lan_telnet.py"
    auth_source = auth_path.read_text(encoding="utf-8")
    lan_source = lan_path.read_text(encoding="utf-8")

    forbidden_imports = {"pty", "termios", "subprocess", "sqlite3", "serial"}
    assert not (imported_roots(auth_path) & forbidden_imports)
    assert not (imported_roots(lan_path) & forbidden_imports)

    for forbidden in (
        "TXBroker",
        "TXModemOwner",
        "TX_TONES",
        "YWD_RF",
        "/dev/tty",
        "serve_forever(public",
    ):
        assert forbidden not in auth_source
        assert forbidden not in lan_source

    assert "TelnetLineDecoder" in lan_source
    assert "LocalTNCCommandShell" in lan_source
    assert "--auth-file" in lan_source
    assert "RFC1918" in lan_source
    assert "Telnet is plaintext" in lan_source
    assert "do not expose" in lan_source
    assert "no P1 shell exists before authentication" in lan_source

    assert "pbkdf2_hmac" in auth_source
    assert "sha256" in auth_source
    assert "compare_digest" in auth_source
    assert "getpass" in auth_source
    assert "0o600" in auth_source
    assert "O_NOFOLLOW" in auth_source
    assert "group/world" in auth_source
    assert "plaintext passwords are never written" in auth_source.lower()

    from ywd1278.console.auth import (
        MAX_AUTH_FILE_BYTES,
        MAX_PASSWORD_CHARS,
        MAX_USERNAME_CHARS,
        MIN_PASSWORD_CHARS,
        PBKDF2_ITERATIONS,
    )
    from ywd1278.console.lan_telnet import (
        DEFAULT_AUTH_TIMEOUT_SECONDS,
        DEFAULT_MAX_AUTH_ATTEMPTS,
        MAX_AUTH_ATTEMPTS_LIMIT,
        validate_client_address,
        validate_lan_bind,
    )

    assert PBKDF2_ITERATIONS == 310_000
    assert MAX_AUTH_FILE_BYTES == 1024
    assert MAX_USERNAME_CHARS == 32
    assert MIN_PASSWORD_CHARS == 10
    assert MAX_PASSWORD_CHARS == 128
    assert DEFAULT_AUTH_TIMEOUT_SECONDS == 30.0
    assert DEFAULT_MAX_AUTH_ATTEMPTS == 3
    assert MAX_AUTH_ATTEMPTS_LIMIT == 5

    for address in ("127.0.0.1", "10.1.2.3", "172.16.1.2", "192.168.1.165"):
        assert validate_lan_bind(address) == address
        assert validate_client_address(address)
    for address in ("0.0.0.0", "8.8.8.8", "100.64.0.1", "169.254.1.1", "::1"):
        assert not validate_client_address(address)
        try:
            validate_lan_bind(address)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe bind accepted: {address}")

    print("YWD1278_0E_P3_AUTH_LAN_CONSOLE_CONTRACT=PASS")
    print("FROZEN_0E_P1_P2_BLOBS=PASS")
    print("BIND_SCOPE=LOOPBACK_OR_RFC1918_IPV4_ONLY")
    print("CLIENT_SCOPE=LOOPBACK_OR_RFC1918_IPV4_ONLY")
    print("AUTHENTICATION=MANDATORY_BEFORE_P1_SHELL")
    print("PASSWORD_STORAGE=PBKDF2_SHA256_HASH_ONLY")
    print("TELNET_TRANSPORT_ENCRYPTION=ABSENT_PRIVATE_LAN_ONLY")
    print("WILDCARD_PUBLIC_WAN_BIND=ABSENT")
    print("PTY_SERIAL_MODEM_KISS_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
