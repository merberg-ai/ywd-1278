#!/usr/bin/env python3
"""Architecture/safety contract for 0E-P5 classic TNC vocabulary."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from ywd1278.console.classic import ClassicTNCCommandShell, make_classic_shell
from ywd1278.console.local import LocalTNCCommandShell


ROOT = Path(__file__).resolve().parents[1]
CLASSIC_PATH = ROOT / "src/ywd1278/console/classic.py"

FROZEN_BLOBS = {
    ROOT / "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    ROOT / "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    ROOT / "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
    ROOT / "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
    ROOT / "src/ywd1278/console/pty_serial.py": "c0ba2a3278ac1e790bf383fc12a220ae327255ba",
    ROOT / "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}

FORBIDDEN_IMPORT_ROOTS = {
    "socket",
    "socketserver",
    "serial",
    "sqlite3",
    "subprocess",
    "termios",
    "tty",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "ywd1278.modem",
    "ywd1278.kiss",
    "ywd1278.tx",
    "ywd1278.runtime",
    "ywd1278.csma",
)
FORBIDDEN_TOKENS = (
    "/dev/ttyAMA",
    "/dev/serial",
    "os.openpty",
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
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def main() -> int:
    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob_sha(path)
        assert actual == expected, f"frozen blob changed: {path}: {actual} != {expected}"

    source = CLASSIC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CLASSIC_PATH))
    for module in imported_modules(tree):
        assert module.split(".", 1)[0] not in FORBIDDEN_IMPORT_ROOTS, module
        assert not module.startswith(FORBIDDEN_IMPORT_PREFIXES), module
    for token in FORBIDDEN_TOKENS:
        assert token not in source, f"forbidden transport/TX token present: {token}"

    required_tokens = (
        "class ClassicTNCCommandShell(LocalTNCCommandShell)",
        '"DISP": "DISPLAY"',
        '"MH": "MHEARD"',
        '"VER": "VERSION"',
        '"STAT": "STATUS"',
        '"HEAL": "HEALTH"',
        '"CONNECT": "0G"',
        '"UNPROTO": "0F"',
        '"CONVERSE": "0F"',
        '"BEACON": "0F"',
        '"XMITOK": "LATER-TX-ENABLE-CONTROL"',
        '"MHCLEAR": "read-only MHEARD boundary"',
        "ambiguous abbreviations are not accepted",
    )
    for token in required_tokens:
        assert token in source, f"required classic safety token missing: {token}"

    shell = make_classic_shell()
    assert isinstance(shell, ClassicTNCCommandShell)
    assert isinstance(shell, LocalTNCCommandShell)
    assert shell.execute("DISP").lines == (
        "DISPLAY MONITOR",
        "MCOM OFF",
        "MCON OFF",
        "MRPT ON",
    )
    assert shell.execute("MH").lines == ("MHEARD UNAVAILABLE",)
    assert "OWNER=0G" in shell.execute("CONNECT KJ6YWD").lines[0]
    assert "OWNER=0F" in shell.execute("UNPROTO CQ").lines[0]
    assert "LATER-TX-COMMAND" in shell.execute("TX hello").lines[0]
    assert "read-only MHEARD boundary" in shell.execute("MHCLEAR").lines[0]
    for ambiguous in ("D", "C", "CON", "MCO", "UNP", "XMIT"):
        assert shell.execute(ambiguous).lines == (
            f"ERROR UNKNOWN COMMAND {ambiguous}",
        )

    print("YWD1278_0E_P5_CLASSIC_VOCABULARY_CONTRACT=PASS")
    print("FROZEN_0E_P1_P2_P3_P4_BLOBS=PASS")
    print("FROZEN_PYPROJECT_BLOB=PASS")
    print("CLASSIC_ADAPTER=SUBCLASS_OF_FROZEN_P1")
    print("SAFE_ALIASES=DISP_MH_VER_STAT_HEAL")
    print("GENERIC_ABBREVIATION_ENGINE=ABSENT")
    print("DISPLAY_SCOPE=MONITOR_ONLY")
    print("MHCLEAR=DISABLED_READ_ONLY")
    print("TX_LINK_COMMANDS=RECOGNIZED_BUT_DEFERRED")
    print("NETWORK_PTY_HARDWARE_SERIAL_OWNERSHIP=ABSENT")
    print("MODEM_KISS_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
