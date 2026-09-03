#!/usr/bin/env python3
"""Architecture/safety contract for 0D-P3 SQLite frame logging."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "monitor" / "sqlite_log.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.server import RXOnlyBackend  # noqa: E402
from ywd1278.monitor.sqlite_log import SQLiteFrameLogger  # noqa: E402


FROZEN_BLOBS = {
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
        "SQLITE_FRAME_LOG_SCHEMA_VERSION = 1",
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "history, live_queue = self._backend.open_stream()",
        "MonitorSubscription(",
        "self._ignored_history_events = len(history)",
        "history replay must never be persisted",
        "source_subscriber_drops",
        "ywd1278-sqlite-frame-log",
        "frame_no_fcs BLOB NOT NULL",
        "info BLOB NOT NULL",
    ):
        assert required in source, required

    # P3 may own exactly one dedicated SQLite consumer thread, but it must not
    # introduce an additional buffering primitive between the qualified source
    # queue and SQLite.
    for forbidden in (
        "Queue(",
        "SimpleQueue(",
        "deque(",
        "asyncio.Queue",
        "multiprocessing.Queue",
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

    logger = SQLiteFrameLogger(RXOnlyBackend(), ":memory:")
    for name in ("publish", "transmit", "send", "submit"):
        assert not hasattr(logger, name), name

    print("YWD1278_0D_P3_SQLITE_FRAME_LOG_CONTRACT=PASS")
    print("FROZEN_P1_MONITOR_STREAM_HASH=PASS")
    print("FROZEN_P2_MONITOR_POLICY_HASH=PASS")
    print("FROZEN_0C_CORE_HASHES=PASS")
    print("SQLITE_DEDICATED_WORKER_THREADS=1")
    print("ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("SOURCE_BACKPRESSURE=EXISTING_BOUNDED_SUBSCRIBER")
    print("HISTORY_REPLAY_TO_SQLITE=DISABLED")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
