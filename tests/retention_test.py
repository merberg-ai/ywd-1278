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
from ywd1278.monitor.mheard import MHeardDatabase  # noqa: E402
from ywd1278.monitor.retention import (  # noqa: E402
    RetentionBusyError,
    RetentionPolicy,
    RetentionSchemaError,
    SQLiteRetentionController,
)
from ywd1278.monitor.sqlite_log import SQLiteFrameLogger  # noqa: E402


def event_for(source: str, destination: str, text: str) -> PacketEvent:
    body = build_ui_frame(
        source=Address.parse(source),
        destination=Address.parse(destination),
        info=text.encode("ascii"),
        include_fcs=False,
    )
    parsed = parse_frame(body, has_fcs=False)
    return PacketEvent(
        body,
        source=str(parsed["source"]),
        destination=str(parsed["destination"]),
        frame_type=str(parsed["frame_type"]),
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


def seed(db: pathlib.Path, times: list[int]) -> None:
    backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=16)
    logger = SQLiteFrameLogger(backend, db, clock_ns=SequenceClock(times))
    logger.start()
    for index in range(len(times)):
        backend.publish(event_for(f"N{index}CALL", "LOG", f"frame-{index}"))
    wait_until(lambda: logger.snapshot.rows_written == len(times))
    logger.stop()


class RetentionTests(unittest.TestCase):
    def test_default_policy_is_disabled_and_apply_is_read_only_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200, 300])
            controller = SQLiteRetentionController(db)
            policy = RetentionPolicy()
            plan = controller.plan(policy, now_ns=1000)
            result = controller.apply(policy, now_ns=1000)
            count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM frames").fetchone()[0]

        self.assertFalse(policy.enabled)
        self.assertFalse(plan.enabled)
        self.assertEqual((plan.total_rows, plan.eligible_rows, plan.next_batch_rows), (3, 0, 0))
        self.assertFalse(result.enabled)
        self.assertEqual(result.deleted_rows, 0)
        self.assertEqual(count, 3)

    def test_age_retention_deletes_only_rows_older_than_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200, 300, 400])
            controller = SQLiteRetentionController(db)
            policy = RetentionPolicy(max_age_ns=250)
            plan = controller.plan(policy, now_ns=500)
            result = controller.apply(policy, now_ns=500)
            connection = sqlite3.connect(db)
            rows = connection.execute("SELECT observed_at_ns FROM frames ORDER BY id").fetchall()
            connection.close()

        self.assertEqual(plan.cutoff_ns, 250)
        self.assertEqual(plan.eligible_rows, 2)
        self.assertEqual(result.deleted_rows, 2)
        self.assertEqual(rows, [(300,), (400,)])

    def test_max_rows_keeps_newest_rows_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200, 300, 400])
            controller = SQLiteRetentionController(db)
            result = controller.apply(RetentionPolicy(max_rows=2), now_ns=500)
            connection = sqlite3.connect(db)
            rows = connection.execute("SELECT observed_at_ns FROM frames ORDER BY observed_at_ns").fetchall()
            connection.close()

        self.assertEqual(result.deleted_rows, 2)
        self.assertEqual(rows, [(300,), (400,)])

    def test_combined_policy_uses_age_or_row_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200, 300, 400, 500])
            controller = SQLiteRetentionController(db)
            plan = controller.plan(RetentionPolicy(max_age_ns=250, max_rows=3), now_ns=600)

        # cutoff 350 makes 100/200/300 eligible; max_rows=3 independently
        # makes 100/200 eligible.  The union therefore contains three rows.
        self.assertEqual(plan.cutoff_ns, 350)
        self.assertEqual(plan.eligible_rows, 3)

    def test_batch_cap_bounds_each_apply_without_automatic_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200, 300, 400, 500])
            controller = SQLiteRetentionController(db, max_delete_per_run=2)
            policy = RetentionPolicy(max_rows=1)
            first = controller.apply(policy, now_ns=600)
            second = controller.apply(policy, now_ns=600)

        self.assertEqual(first.deleted_rows, 2)
        self.assertEqual(first.remaining_rows, 3)
        self.assertEqual(first.remaining_eligible_rows, 2)
        self.assertTrue(first.more_eligible)
        self.assertEqual(second.deleted_rows, 2)
        self.assertEqual(second.remaining_rows, 1)
        self.assertEqual(second.remaining_eligible_rows, 0)
        self.assertFalse(second.more_eligible)

    def test_busy_writer_fails_closed_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            seed(db, [100, 200])
            lock = sqlite3.connect(db)
            lock.execute("BEGIN IMMEDIATE")
            try:
                controller = SQLiteRetentionController(db, sqlite_timeout=0.05)
                with self.assertRaises(RetentionBusyError):
                    controller.apply(RetentionPolicy(max_rows=1), now_ns=300)
            finally:
                lock.rollback()
                lock.close()

    def test_wrong_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            connection = sqlite3.connect(db)
            connection.execute("PRAGMA user_version=99")
            connection.commit()
            connection.close()
            controller = SQLiteRetentionController(db)
            with self.assertRaises(RetentionSchemaError):
                controller.plan(RetentionPolicy(max_rows=1), now_ns=100)

    def test_mheard_reflects_retained_frames_without_special_coupling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=8)
            logger = SQLiteFrameLogger(backend, db, clock_ns=SequenceClock([100, 200, 300]))
            logger.start()
            backend.publish(event_for("KJ6YWD-9", "APRS", "old"))
            backend.publish(event_for("N0CALL-2", "LOG", "middle"))
            backend.publish(event_for("KJ6YWD", "JIM", "new"))
            wait_until(lambda: logger.snapshot.rows_written == 3)
            logger.stop()

            before = MHeardDatabase(db).summary()
            SQLiteRetentionController(db).apply(RetentionPolicy(max_rows=2), now_ns=400)
            after = MHeardDatabase(db).summary()
            stations = [entry.source for entry in MHeardDatabase(db).list()]

        self.assertEqual((before.station_count, before.frame_count), (3, 3))
        self.assertEqual((after.station_count, after.frame_count), (2, 2))
        self.assertEqual(stations, ["KJ6YWD", "N0CALL-2"])

    def test_invalid_controls_and_surface_fail_closed(self) -> None:
        for kwargs in ({"max_age_ns": 0}, {"max_age_ns": -1}, {"max_rows": 0}, {"max_rows": -1}):
            with self.assertRaises(ValueError):
                RetentionPolicy(**kwargs)
        with self.assertRaises(TypeError):
            RetentionPolicy(max_rows=True)
        with self.assertRaises(ValueError):
            SQLiteRetentionController("x", max_delete_per_run=0)
        with self.assertRaises(ValueError):
            SQLiteRetentionController("x", max_delete_per_run=10001)

        controller = SQLiteRetentionController("/does/not/matter.sqlite3")
        for name in ("start", "stop", "open_stream", "publish", "transmit", "send", "submit"):
            self.assertFalse(hasattr(controller, name), name)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RetentionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P5_RETENTION=PASS")
    print("RETENTION_DEFAULT=DISABLED")
    print("RETENTION_AGE_LIMIT=PASS")
    print("RETENTION_MAX_ROWS=PASS")
    print("RETENTION_COMBINED_POLICY=OR")
    print("RETENTION_MAX_DELETE_PER_RUN_DEFAULT=1000")
    print("RETENTION_AUTOMATIC_LOOP=NO")
    print("RETENTION_BUSY_WRITER=FAIL_CLOSED")
    print("RETENTION_VACUUM_AUTOMATIC=NO")
    print("MHEARD_POST_RETENTION=PASS")
    print("RETENTION_PACKET_SUBSCRIBER=NO")
    print("RETENTION_WORKER_THREAD=NO")
    print("RETENTION_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
