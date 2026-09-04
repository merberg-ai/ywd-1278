#!/usr/bin/env python3
"""Architecture/safety contract for 0D-P4 read-only MHEARD."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "monitor" / "mheard.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.monitor.mheard import MHeardDatabase  # noqa: E402


FROZEN_BLOBS = {
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
    "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
    "src/ywd1278/kiss/sustained.py": "63cf33f4b6d4cedd091af0349a8037669d45e84d",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/rx_runtime.py": "ea63eb82cb82ed273cab8d393aedf797b46ff123",
    "src/ywd1278/service/tnc_runtime.py": "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1",
}


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    source = MODULE.read_text(encoding="utf-8")
    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    for required in (
        "?mode=ro",
        "PRAGMA query_only=ON",
        "SQLITE_FRAME_LOG_SCHEMA_VERSION",
        "COUNT(*) OVER (PARTITION BY source)",
        "MIN(observed_at_ns) OVER (PARTITION BY source)",
        "MAX(observed_at_ns) OVER (PARTITION BY source)",
        "ROW_NUMBER() OVER",
        "ORDER BY observed_at_ns DESC, id DESC",
        "COUNT(DISTINCT source)",
        "1 <= limit <= 1000",
    ):
        assert required in source, required

    for forbidden in (
        "from ywd1278.kiss",
        "import ywd1278.kiss",
        "from .stream import MonitorSubscription",
        "import threading",
        "from threading import",
        "Thread(",
        "Queue(",
        "SimpleQueue(",
        "deque(",
        "asyncio.Queue",
        "multiprocessing.Queue",
        "INSERT INTO",
        "UPDATE frames",
        "DELETE FROM",
        "CREATE TABLE",
        "DROP TABLE",
        "ywd1278.modem",
        "ywd1278.tx",
        "TXBroker",
        "TXModemOwner",
        "ModemOwner",
        "posix_serial_transport_factory",
        "/dev/tty",
        "RPi.GPIO",
        "gpiozero",
        ".transmit_selector_burst(",
        ".transact(",
        "rx_start(",
        "rx_stop(",
    ):
        assert forbidden not in source, forbidden

    heard = MHeardDatabase("/does/not/matter.sqlite3")
    for name in (
        "start",
        "stop",
        "open_stream",
        "publish",
        "transmit",
        "send",
        "submit",
        "delete",
        "clear",
    ):
        assert not hasattr(heard, name), name

    print("YWD1278_0D_P4_MHEARD_CONTRACT=PASS")
    print("FROZEN_P3_SQLITE_LOG_HASH=PASS")
    print("FROZEN_P1_MONITOR_STREAM_HASH=PASS")
    print("FROZEN_P2_MONITOR_POLICY_HASH=PASS")
    print("FROZEN_0C_CORE_HASHES=PASS")
    print("MHEARD_SQLITE_MODE=READ_ONLY_QUERY_ONLY")
    print("MHEARD_SOURCE=QUALIFIED_P3_FRAMES_TABLE")
    print("MHEARD_ADDITIONAL_PACKET_SUBSCRIBER=NO")
    print("MHEARD_ADDITIONAL_WORKER_THREAD=NO")
    print("MHEARD_ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("MHEARD_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("MHEARD_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
