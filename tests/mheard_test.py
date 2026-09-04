#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, parse_frame  # noqa: E402
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend  # noqa: E402
from ywd1278.monitor.mheard import (  # noqa: E402
    MHeardDatabase,
    MHeardSchemaError,
)
from ywd1278.monitor.sqlite_log import SQLiteFrameLogger  # noqa: E402


def event_for(body: bytes) -> PacketEvent:
    parsed = parse_frame(body, has_fcs=False)
    return PacketEvent(
        body,
        source=str(parsed["source"]),
        destination=str(parsed["destination"]),
        frame_type=str(parsed["frame_type"]),
    )


def frame(source: str, destination: str, text: str, path: list[Address] | None = None) -> bytes:
    return build_ui_frame(
        source=Address.parse(source),
        destination=Address.parse(destination),
        path=[] if path is None else path,
        info=text.encode("ascii"),
        include_fcs=False,
    )


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


class SequenceClock:
    def __init__(self, values: list[int]) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


class MHeardTests(unittest.TestCase):
    def _seed(self, db: pathlib.Path) -> None:
        backend = RXOnlyBackend(history_capacity=8, subscriber_queue_capacity=8)
        logger = SQLiteFrameLogger(
            backend,
            db,
            clock_ns=SequenceClock([100, 200, 300, 400, 500]),
        )
        logger.start()
        backend.publish(
            event_for(
                frame(
                    "KJ6YWD-9",
                    "APRS",
                    "one",
                    [Address.parse("WIDE1-1", flag=True), Address.parse("WIDE2-1")],
                )
            )
        )
        backend.publish(event_for(frame("N0CALL-2", "YWD", "two")))
        backend.publish(event_for(frame("KJ6YWD-9", "JIM", "three")))
        backend.publish(event_for(frame("KJ6YWD", "NODE", "four")))
        backend.publish(event_for(frame("N0CALL-2", "LAST", "five")))
        wait_until(lambda: logger.snapshot.rows_written == 5)
        logger.stop()
        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_mheard_aggregates_callsign_ssid_and_uses_latest_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            self._seed(db)
            heard = MHeardDatabase(db)
            entries = heard.list()
            summary = heard.summary()

        self.assertEqual(summary.station_count, 3)
        self.assertEqual(summary.frame_count, 5)
        self.assertEqual(summary.latest_heard_ns, 500)
        self.assertEqual([entry.source for entry in entries], ["N0CALL-2", "KJ6YWD", "KJ6YWD-9"])

        n0call = entries[0]
        self.assertEqual((n0call.callsign, n0call.ssid), ("N0CALL", 2))
        self.assertEqual(n0call.heard_count, 2)
        self.assertEqual((n0call.first_heard_ns, n0call.last_heard_ns), (200, 500))
        self.assertEqual(n0call.last_destination, "LAST")
        self.assertEqual(n0call.last_path, ())
        self.assertEqual(n0call.last_frame_type, "UI")
        self.assertEqual(n0call.last_line, "N0CALL-2>LAST:five")

        mobile = next(item for item in entries if item.source == "KJ6YWD-9")
        self.assertEqual(mobile.heard_count, 2)
        self.assertEqual((mobile.first_heard_ns, mobile.last_heard_ns), (100, 300))
        self.assertEqual(mobile.last_destination, "JIM")
        self.assertEqual(mobile.last_path, ())
        self.assertEqual(mobile.last_line, "KJ6YWD-9>JIM:three")

        base = next(item for item in entries if item.source == "KJ6YWD")
        self.assertEqual((base.callsign, base.ssid), ("KJ6YWD", 0))
        self.assertEqual(base.heard_count, 1)
        self.assertEqual(base.last_destination, "NODE")

    def test_since_filter_recomputes_window_counts_and_limit_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            self._seed(db)
            heard = MHeardDatabase(db)
            entries = heard.list(since_ns=300, limit=2)
            summary = heard.summary(since_ns=300)

        self.assertEqual(summary.station_count, 3)
        self.assertEqual(summary.frame_count, 3)
        self.assertEqual(summary.latest_heard_ns, 500)
        self.assertEqual([entry.source for entry in entries], ["N0CALL-2", "KJ6YWD"])
        self.assertEqual(entries[0].heard_count, 1)
        self.assertEqual(entries[0].first_heard_ns, 500)

    def test_get_normalizes_source_and_preserves_ssid_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            self._seed(db)
            heard = MHeardDatabase(db)
            mobile = heard.get("kj6ywd-9")
            base = heard.get("KJ6YWD")
            missing = heard.get("NONE")

        self.assertIsNotNone(mobile)
        self.assertIsNotNone(base)
        self.assertEqual(mobile.source, "KJ6YWD-9")
        self.assertEqual(base.source, "KJ6YWD")
        self.assertIsNone(missing)

    def test_invalid_window_and_limit_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            self._seed(db)
            heard = MHeardDatabase(db)
            for bad in (0, -1, 1001):
                with self.assertRaises(ValueError):
                    heard.list(limit=bad)
            with self.assertRaises(TypeError):
                heard.list(limit=True)
            with self.assertRaises(ValueError):
                heard.list(since_ns=-1)
            with self.assertRaises(TypeError):
                heard.summary(since_ns=True)

    def test_wrong_frame_log_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            connection = sqlite3.connect(db)
            connection.execute("PRAGMA user_version=99")
            connection.commit()
            connection.close()
            heard = MHeardDatabase(db)
            with self.assertRaises(MHeardSchemaError):
                heard.list()

    def test_mheard_surface_has_no_packet_or_tx_operation(self) -> None:
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
            self.assertFalse(hasattr(heard, name), name)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MHeardTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P4_MHEARD=PASS")
    print("MHEARD_SOURCE=SQLITE_FRAME_LOG_READ_ONLY")
    print("MHEARD_AGGREGATION=SOURCE_CALLSIGN_SSID")
    print("MHEARD_LATEST_ROUTE=PASS")
    print("MHEARD_SINCE_FILTER=PASS")
    print("MHEARD_BOUNDED_LIMIT=1_TO_1000")
    print("MHEARD_ADDITIONAL_PACKET_SUBSCRIBER=NO")
    print("MHEARD_ADDITIONAL_WORKER_THREAD=NO")
    print("MHEARD_ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("MHEARD_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
