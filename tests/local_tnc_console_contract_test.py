#!/usr/bin/env python3
"""Architecture/safety contract for the 0E-P1 local classic TNC shell."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "console" / "local.py"
PYPROJECT = ROOT / "pyproject.toml"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.console.local import (  # noqa: E402
    MAX_COMMAND_CHARS,
    MAX_MHEARD_LIMIT,
    LocalTNCCommandShell,
)


FROZEN_BLOBS = {
    "src/ywd1278/monitor/diagnostics.py": "0f23c1232b51e2f5fbd1a3d4c179e0c94ce4116a",
    "src/ywd1278/monitor/mheard.py": "09a9dd17cee8eff2ef9aa3df418a3e575e1f985e",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
    "src/ywd1278/monitor/retention.py": "1e08367d98f39e15eaeb855ef5e6e6b39eef9302",
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
    "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
    "src/ywd1278/kiss/sustained.py": "63cf33f4b6d4cedd091af0349a8037669d45e84d",
    "src/ywd1278/kiss/tx_backend.py": "e06c1a619a02ecb4cf2073a3f270be1b2d54ea0e",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/tnc_runtime.py": "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1",
}


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    for required in (
        "class CommandResult",
        "class LocalTNCCommandShell",
        "def execute(self, line: str)",
        'command in ("HELP", "?")',
        'command == "VERSION"',
        'command == "STATUS"',
        'command == "HEALTH"',
        'command == "MHEARD"',
        'command in ("MCOM", "MCON", "MRPT")',
        'command in ("QUIT", "EXIT")',
        'return CommandResult((f"ERROR UNKNOWN COMMAND {command}",))',
        "def run_local_console(",
        'PROMPT = "cmd:"',
        "readline(MAX_COMMAND_CHARS + 2)",
        "MHeardDatabase(args.database)",
        "DiagnosticsStatus(mheard_db=mheard)",
        'ywd1278-console = "ywd1278.console.local:main"',
    ):
        assert required in (source + "\n" + pyproject), required

    for forbidden in (
        "import socket",
        "from socket import",
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
        "from ywd1278.tx",
        "import ywd1278.tx",
        "TXBroker",
        "TXModemOwner",
        "ModemOwner",
        "posix_serial_transport_factory",
        "/dev/tty",
        "RPi.GPIO",
        "gpiozero",
        ".open_stream(",
        ".publish(",
        ".enqueue(",
        ".observe_rssi(",
        ".submit_frame(",
        ".transmit_selector_burst(",
        ".transact(",
        "rx_start(",
        "rx_stop(",
        "sqlite3.connect",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "VACUUM",
        "wal_checkpoint",
        "Thread(",
        "Queue(",
        "asyncio",
    ):
        assert forbidden not in source, forbidden

    assert MAX_COMMAND_CHARS == 256
    assert MAX_MHEARD_LIMIT == 100

    shell = LocalTNCCommandShell(version="contract")
    assert shell.execute("VERSION").lines == ("YWD-1278 contract",)
    assert shell.execute("STATUS").lines == ("STATUS UNAVAILABLE",)
    assert shell.execute("HEALTH").lines == ("HEALTH UNAVAILABLE",)
    assert shell.execute("MHEARD").lines == ("MHEARD UNAVAILABLE",)
    assert shell.execute("MCOM").lines == ("MCOM OFF",)
    assert shell.execute("MCON").lines == ("MCON OFF",)
    assert shell.execute("MRPT").lines == ("MRPT ON",)
    assert shell.execute("CONNECT KJ6YWD").lines == ("ERROR UNKNOWN COMMAND CONNECT",)
    assert shell.execute("CONVERSE").lines == ("ERROR UNKNOWN COMMAND CONVERSE",)
    assert shell.execute("UNPROTO APRS").lines == ("ERROR UNKNOWN COMMAND UNPROTO",)
    assert shell.execute("BEACON").lines == ("ERROR UNKNOWN COMMAND BEACON",)
    assert shell.execute("TX hi").lines == ("ERROR UNKNOWN COMMAND TX",)

    for name in (
        "start",
        "stop",
        "open_stream",
        "publish",
        "transmit",
        "send",
        "submit",
        "apply",
        "enqueue",
        "observe_rssi",
        "connect",
    ):
        assert not hasattr(shell, name), name

    print("YWD1278_0E_P1_LOCAL_TNC_CONSOLE_CONTRACT=PASS")
    print("FROZEN_0D_P6_DIAGNOSTICS_HASH=PASS")
    print("FROZEN_0D_P5_RETENTION_HASH=PASS")
    print("FROZEN_0D_P4_MHEARD_HASH=PASS")
    print("FROZEN_0D_P1_P3_MONITOR_HASHES=PASS")
    print("FROZEN_0C_RUNTIME_HASHES=PASS")
    print("LOCAL_CONSOLE_STDIN_STDOUT_ONLY=YES")
    print("LOCAL_CONSOLE_NETWORK_LISTENER=NO")
    print("LOCAL_CONSOLE_PTY_SERIAL=NO")
    print("LOCAL_CONSOLE_SHELL_ESCAPE=NO")
    print("LOCAL_CONSOLE_DYNAMIC_EXECUTION=NO")
    print("LOCAL_CONSOLE_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("LOCAL_CONSOLE_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
