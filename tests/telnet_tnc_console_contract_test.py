#!/usr/bin/env python3
"""Architecture/safety contract for the 0E-P2 loopback Telnet console."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "console" / "telnet.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.console.local import LocalTNCCommandShell  # noqa: E402
from ywd1278.console.telnet import (  # noqa: E402
    DEFAULT_BIND_ADDRESS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_MAX_CLIENTS,
    DEFAULT_MAX_COMMANDS,
    DEFAULT_MAX_SESSION_SECONDS,
    DEFAULT_PORT,
    MAX_CLIENTS_LIMIT,
    MAX_COMMANDS_LIMIT,
    MAX_TELNET_NEGOTIATIONS,
    RECV_CHUNK_BYTES,
    TelnetLineDecoder,
    TelnetTNCServer,
)


FROZEN_0E_P1_BLOBS = {
    "src/ywd1278/console/__init__.py": "63509fc8dc0c9c91bd8415123ae93b45cd1ecf01",
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "tests/local_tnc_console_test.py": "4fa6dbbf1e6649646eec0ff4f086726832ff3849",
    "tests/local_tnc_console_contract_test.py": "aa5199481cc8307b315ef0045b16956905814246",
    "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")

    for path, expected in FROZEN_0E_P1_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    for required in (
        "class TelnetLineDecoder",
        "class TelnetTNCServer",
        "socketserver.ThreadingMixIn",
        "threading.BoundedSemaphore",
        "def _validate_loopback_bind(address: str)",
        "LocalTNCCommandShell",
        "shell = server.shell_factory()",
        "sock.recv(RECV_CHUNK_BYTES)",
        'DEFAULT_BIND_ADDRESS = "127.0.0.1"',
        "DEFAULT_PORT = 8023",
        "MAX_TELNET_NEGOTIATIONS = 32",
        "daemon_threads = True",
        "max_session_seconds",
        "idle_timeout_seconds",
        "max_commands",
        "MHeardDatabase(database_path)",
        "DiagnosticsStatus(mheard_db=mheard)",
        "MonitorPolicyState()",
        "0E-P2 loopback-only command mode",
    ):
        assert required in source, required

    for forbidden in (
        "import pty",
        "from pty import",
        "import termios",
        "from termios import",
        "import subprocess",
        "from subprocess import",
        "os.system",
        "os.popen",
        "eval(",
        "exec(",
        "compile(",
        "__import__(",
        "ywd1278.modem",
        "ywd1278.kiss",
        "from ywd1278.tx",
        "import ywd1278.tx",
        "TXBroker",
        "TXModemOwner",
        "ModemOwner",
        "posix_serial_transport_factory",
        "/dev/tty",
        "RPi.GPIO",
        "gpiozero",
        "sqlite3.connect",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "VACUUM",
        "wal_checkpoint",
        ".publish(",
        ".enqueue(",
        ".submit_frame(",
        ".transmit_selector_burst(",
        ".transact(",
        "rx_start(",
        "rx_stop(",
        ".apply(",
        "Queue(",
        "asyncio",
    ):
        assert forbidden not in source, forbidden

    assert DEFAULT_BIND_ADDRESS == "127.0.0.1"
    assert DEFAULT_PORT == 8023
    assert DEFAULT_MAX_CLIENTS == 4
    assert DEFAULT_IDLE_TIMEOUT_SECONDS == 300.0
    assert DEFAULT_MAX_SESSION_SECONDS == 3600.0
    assert DEFAULT_MAX_COMMANDS == 1024
    assert MAX_CLIENTS_LIMIT == 16
    assert MAX_COMMANDS_LIMIT == 10000
    assert MAX_TELNET_NEGOTIATIONS == 32
    assert RECV_CHUNK_BYTES == 512

    for address in ("0.0.0.0", "192.168.1.10", "8.8.8.8", "::1", "localhost"):
        try:
            TelnetTNCServer(
                (address, 0),
                shell_factory=lambda: LocalTNCCommandShell(version="contract"),
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"non-loopback bind accepted: {address}")

    server = TelnetTNCServer(
        (DEFAULT_BIND_ADDRESS, 0),
        shell_factory=lambda: LocalTNCCommandShell(version="contract"),
    )
    try:
        assert server.server_address[0] == DEFAULT_BIND_ADDRESS
        assert server.max_clients == DEFAULT_MAX_CLIENTS
        assert server.idle_timeout_seconds == DEFAULT_IDLE_TIMEOUT_SECONDS
        assert server.max_session_seconds == DEFAULT_MAX_SESSION_SECONDS
        assert server.max_commands == DEFAULT_MAX_COMMANDS
    finally:
        server.server_close()

    decoder = TelnetLineDecoder()
    result = decoder.feed(bytes((255, 251, 1)) + b"VERSION\r\n")
    assert result.replies == bytes((255, 254, 1))
    assert result.events[0].line == "VERSION"
    assert result.fatal_error is None

    shell = LocalTNCCommandShell(version="contract")
    for text in (
        "CONNECT KJ6YWD",
        "CONVERSE",
        "UNPROTO APRS",
        "BEACON",
        "TX hi",
        "SEND hi",
        "TRANSMIT hi",
        "KISS ON",
        "SHELL",
    ):
        result = shell.execute(text)
        assert result.lines[0].startswith("ERROR UNKNOWN COMMAND "), text

    print("YWD1278_0E_P2_TELNET_CONSOLE_CONTRACT=PASS")
    print("FROZEN_0E_P1_BLOBS=PASS")
    print("TELNET_BIND_IPV4_LOOPBACK_ONLY=YES")
    print("TELNET_DEFAULT_PORT=8023")
    print("TELNET_MAX_CLIENTS_DEFAULT=4")
    print("TELNET_IDLE_TIMEOUT_SECONDS=300")
    print("TELNET_MAX_SESSION_SECONDS=3600")
    print("TELNET_MAX_COMMANDS_DEFAULT=1024")
    print("TELNET_NEGOTIATIONS_MAX=32")
    print("TELNET_RECV_CHUNK_BYTES=512")
    print("P1_PARSER_REUSED=YES")
    print("P1_PARSER_MODIFIED=NO")
    print("REMOTE_OR_WILDCARD_BIND=ABSENT")
    print("AUTHENTICATION_REQUIRED_FOR_BROADER_BIND=PENDING_SEPARATE_GATE")
    print("PTY_SERIAL=ABSENT")
    print("DATABASE_WRITE_RETENTION_APPLY=ABSENT")
    print("MODEM_UART_KISS_TX_CAPABILITY=ABSENT")
    print("RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
