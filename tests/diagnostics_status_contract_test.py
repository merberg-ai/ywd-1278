#!/usr/bin/env python3
"""Architecture/safety contract for 0D-P6 diagnostics/status aggregation."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "monitor" / "diagnostics.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.monitor.diagnostics import DiagnosticsStatus  # noqa: E402


FROZEN_BLOBS = {
    "src/ywd1278/monitor/retention.py": "1e08367d98f39e15eaeb855ef5e6e6b39eef9302",
    "src/ywd1278/monitor/mheard.py": "09a9dd17cee8eff2ef9aa3df418a3e575e1f985e",
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
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
    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    for required in (
        "class DiagnosticsSnapshot",
        "class DiagnosticsStatus",
        "runtime_accounting = _read(self._runtime, \"accounting\")",
        "runtime_counters = _read(self._runtime, \"runtime_counters\")",
        "backend_map = _mapping(_read(self._backend, \"snapshot\"))",
        "parameters = _mapping(_read(self._backend, \"control_snapshot\"))",
        "control = _mapping(_read(self._backend, \"control_counters\"))",
        "ingress = _mapping(_read(self._backend, \"ingress_counters\"))",
        "connections = _mapping(_read(self._backend, \"connection_counters\"))",
        "sqlite_map = _mapping(_read(self._sqlite_logger, \"snapshot\"))",
        "mheard_map = _mapping(self._mheard_db.summary())",
        "self._retention_controller.plan(",
        'problems.append("runtime-failure")',
        'problems.append("subscriber-drops")',
        'problems.append("tx-access-timeouts")',
        'problems.append("tx-downstream-failures")',
        'problems.append("sqlite-write-failures")',
        'problems.append("sqlite-fatal-error")',
        "healthy=not problems",
    ):
        assert required in source, required

    for forbidden in (
        "import threading",
        "from threading import",
        "import queue",
        "from queue import",
        "Thread(",
        "Queue(",
        "SimpleQueue(",
        "deque(",
        "asyncio.Queue",
        "multiprocessing.Queue",
        "sqlite3.connect",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "VACUUM",
        "wal_checkpoint",
        "ywd1278.modem",
        "ywd1278.tx",
        "TXBroker",
        "TXModemOwner",
        "ModemOwner",
        "posix_serial_transport_factory",
        "/dev/tty",
        "RPi.GPIO",
        "gpiozero",
        ".apply(",
        ".publish(",
        ".open_stream(",
        ".enqueue(",
        ".observe_rssi(",
        ".submit_frame(",
        ".transmit_selector_burst(",
        ".transact(",
        "rx_start(",
        "rx_stop(",
    ):
        assert forbidden not in source, forbidden

    status = DiagnosticsStatus()
    snap = status.snapshot()
    assert snap.healthy is True
    assert snap.problems == ()
    assert snap.runtime is None
    assert snap.backend is None

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
    ):
        assert not hasattr(status, name), name

    print("YWD1278_0D_P6_DIAGNOSTICS_STATUS_CONTRACT=PASS")
    print("FROZEN_P5_RETENTION_HASH=PASS")
    print("FROZEN_P4_MHEARD_HASH=PASS")
    print("FROZEN_P3_SQLITE_LOG_HASH=PASS")
    print("FROZEN_P1_P2_MONITOR_HASHES=PASS")
    print("FROZEN_0C_RUNTIME_COUNTER_SOURCES=PASS")
    print("DIAGNOSTICS_SAMPLING_THREAD=NO")
    print("DIAGNOSTICS_PACKET_SUBSCRIBER=NO")
    print("DIAGNOSTICS_ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("DIAGNOSTICS_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("DIAGNOSTICS_RETENTION_APPLY_CAPABILITY=ABSENT")
    print("DIAGNOSTICS_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
