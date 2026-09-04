#!/usr/bin/env python3
"""Architecture contract for the 0E-P4 local virtual PTY TNC personality."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PTY_PATH = ROOT / "src/ywd1278/console/pty_serial.py"
P1_PATH = ROOT / "src/ywd1278/console/local.py"
P2_PATH = ROOT / "src/ywd1278/console/telnet.py"
P3_AUTH_PATH = ROOT / "src/ywd1278/console/auth.py"
P3_LAN_PATH = ROOT / "src/ywd1278/console/lan_telnet.py"
PYPROJECT_PATH = ROOT / "pyproject.toml"

FROZEN_BLOBS = {
    P1_PATH: "9fed5416ca9123811413f4ef284abff0006a48dd",
    P2_PATH: "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    P3_AUTH_PATH: "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
    P3_LAN_PATH: "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
    PYPROJECT_PATH: "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}

FORBIDDEN_IMPORT_ROOTS = {
    "socket",
    "socketserver",
    "serial",
    "sqlite3",
    "subprocess",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "ywd1278.modem",
    "ywd1278.kiss",
    "ywd1278.tx",
    "ywd1278.runtime",
)
FORBIDDEN_TOKENS = (
    "/dev/ttyAMA0",
    "/dev/serial0",
    "/dev/serial",
    "TXBroker",
    "TXModemOwner",
    "TX_TONES",
    "YWD_RF",
    "YWD_RX",
    "RPi.GPIO",
    "gpiod",
)


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob_sha(path)
        assert actual == expected, f"frozen blob changed: {path}: {actual} != {expected}"

    source = PTY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PTY_PATH))
    imports = imported_modules(tree)

    for module in imports:
        root = module.split(".", 1)[0]
        assert root not in FORBIDDEN_IMPORT_ROOTS, f"forbidden import: {module}"
        assert not module.startswith(FORBIDDEN_IMPORT_PREFIXES), (
            f"forbidden YWD runtime import: {module}"
        )

    for token in FORBIDDEN_TOKENS:
        assert token not in source, f"forbidden hardware/TX token present: {token}"

    required_tokens = (
        "os.openpty()",
        "os.ttyname(slave_fd)",
        "tty.setraw(slave_fd",
        "os.chmod(slave_path, PTY_MODE)",
        "PTY_MODE = 0o600",
        "os.path.lexists(self.link_path)",
        "os.symlink(slave_path, self.link_path)",
        "LocalTNCCommandShell",
        "MonitorPolicyState()",
        "MAX_COMMAND_CHARS",
        "SerialLineDecoder",
    )
    for token in required_tokens:
        assert token in source, f"required PTY safety/composition token missing: {token}"

    print("YWD1278_0E_P4_VIRTUAL_PTY_CONTRACT=PASS")
    print("FROZEN_0E_P1_P2_P3_BLOBS=PASS")
    print("FROZEN_PYPROJECT_BLOB=PASS")
    print("PTY_IMPLEMENTATION=KERNEL_OPENPTY_ONLY")
    print("PTY_SLAVE_MODE=0600")
    print("STABLE_LINK=OPT_IN_ABSOLUTE_NO_REPLACE_CLEANUP")
    print("P1_COMMAND_PARSER=UNCHANGED")
    print("NETWORK_LISTENER=ABSENT")
    print("HARDWARE_SERIAL=ABSENT")
    print("DATABASE_WRITE=ABSENT")
    print("MODEM_KISS_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
