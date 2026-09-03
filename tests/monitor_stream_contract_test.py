#!/usr/bin/env python3
"""Architecture/safety contract for 0D-P1 decoded monitor stream."""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MONITOR = ROOT / "src" / "ywd1278" / "monitor" / "stream.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.server import RXOnlyBackend  # noqa: E402
from ywd1278.monitor import DecodedMonitorStream  # noqa: E402


FROZEN_BLOBS = {
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
    source = MONITOR.read_text(encoding="utf-8")

    for path, expected in FROZEN_BLOBS.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    for forbidden in (
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
        "set_rx_frequency(",
        "set_tx_frequency(",
    ):
        assert forbidden not in source, forbidden

    # One subscription must be one existing bounded backend queue.  There is
    # deliberately no monitor worker thread and no second Queue construction.
    assert "self._backend.open_stream()" in source
    assert "self._backend.close_stream(self._live_queue)" in source
    assert "threading" not in source
    assert "Queue(" not in source
    assert "source_subscriber_drops=self._backend.snapshot.subscriber_drops" in source

    backend = RXOnlyBackend(history_capacity=4, subscriber_queue_capacity=2)
    stream = DecodedMonitorStream(backend)
    assert not hasattr(stream, "publish")
    assert not hasattr(stream, "transmit")
    sub = stream.open()
    try:
        assert backend.snapshot.subscribers == 1
        assert not hasattr(sub, "publish")
        assert not hasattr(sub, "transmit")
    finally:
        sub.close()
    assert backend.snapshot.subscribers == 0

    print("YWD1278_0D_P1_MONITOR_CONTRACT=PASS")
    print("FROZEN_0C_CORE_HASHES=PASS")
    print("MONITOR_PACKETEVENT_SUBSCRIBER_ONLY=PASS")
    print("MONITOR_ADDITIONAL_WORKER_THREAD=NO")
    print("MONITOR_ADDITIONAL_QUEUE=NO")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
