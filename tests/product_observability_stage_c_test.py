#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import socket
import tempfile
import unittest

from product_daemon_stage_b_test import (
    StageBTransport,
    body,
    config_text as stage_b_config_text,
    free_port,
    recv_data,
    rx_capture,
    wait_until,
)
from ywd1278.kiss.framing import DATA, encode
from ywd1278.service.appliance import (
    ProductConfigurationError,
    ProductPacketEngine,
    load_product_packet_engine_config,
)


def stage_c_config_text(
    *,
    database: Path | None,
    monitor_enabled: bool = True,
    log_frames: bool = True,
    kiss_enabled: bool = True,
) -> str:
    base = stage_b_config_text(
        port=free_port(),
        tx_enabled=False,
        tx_power=64,
        kiss_enabled=kiss_enabled,
    )
    text = base + f'''\n[monitor]\nenabled = {str(monitor_enabled).lower()}\nlog_frames = {str(log_frames).lower()}\n'''
    if database is not None:
        text += f'''\n[storage]\ndatabase = "{database}"\n'''
    return text


def write_stage_c_config(
    directory: str,
    *,
    database: Path | None,
    monitor_enabled: bool = True,
    log_frames: bool = True,
    kiss_enabled: bool = True,
) -> Path:
    path = Path(directory) / "stage-c.toml"
    path.write_text(
        stage_c_config_text(
            database=database,
            monitor_enabled=monitor_enabled,
            log_frames=log_frames,
            kiss_enabled=kiss_enabled,
        ),
        encoding="utf-8",
    )
    return path


class StageCProductObservabilityTests(unittest.TestCase):
    def test_configuration_and_typed_boundary_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cases = [
                {
                    "database": None,
                    "monitor_enabled": True,
                    "log_frames": True,
                    "message": "storage",
                },
                {
                    "database": root / "frames.sqlite3",
                    "monitor_enabled": False,
                    "log_frames": True,
                    "message": "monitor.enabled",
                },
            ]
            for index, case in enumerate(cases):
                with self.subTest(index=index):
                    message = str(case.pop("message"))
                    path = write_stage_c_config(td, **case)
                    with self.assertRaisesRegex(ProductConfigurationError, message):
                        load_product_packet_engine_config(path)

            path = write_stage_c_config(
                td,
                database=root / "frames.sqlite3",
                monitor_enabled=True,
                log_frames=True,
            )
            config = load_product_packet_engine_config(path)
            self.assertTrue(config.monitor_enabled)
            self.assertTrue(config.monitor_log_frames)
            self.assertEqual(config.database_path, root / "frames.sqlite3")

            # The capability-owning object revalidates typed callers; bypassing
            # the TOML loader cannot authorize an unqualified TX profile.
            unsafe = replace(config, tx_enabled=True, frequency_hz=145_060_000)
            with self.assertRaisesRegex(ProductConfigurationError, "145.050"):
                ProductPacketEngine(unsafe, transport_factory=lambda: StageBTransport())

    def test_rx_reaches_kiss_monitor_sqlite_mheard_and_diagnostics(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            database = Path(td) / "frames.sqlite3"
            path = write_stage_c_config(td, database=database)
            config = load_product_packet_engine_config(path)
            engine = ProductPacketEngine(
                config,
                transport_factory=factory,
                random_byte_source=lambda: 0,
            )
            engine.start()
            monitor = engine.open_monitor()
            try:
                self.assertTrue(engine.snapshot.running)
                self.assertTrue(database.exists())
                assert engine.observability is not None
                self.assertTrue(engine.observability.snapshot.logger_running)

                assert engine.kiss_server is not None
                host, port = engine.kiss_server.server_address[:2]
                with socket.create_connection((host, int(port)), timeout=1.0) as client:
                    inbound = body("STAGE C OBSERVABILITY")
                    created[0].inject_rx_packed(rx_capture(inbound))

                    kiss_message = recv_data(client)
                    self.assertEqual(kiss_message.frame, inbound)

                    record = monitor.get(timeout=4.0)
                    self.assertFalse(record.history_replay)
                    self.assertEqual(record.source, "KJ6YWD-10")
                    self.assertEqual(record.destination, "YWDB")
                    self.assertEqual(record.path, ("YWDNOD",))
                    self.assertIn("STAGE C OBSERVABILITY", record.line)

                    wait_until(
                        lambda: engine.observability is not None
                        and engine.observability.snapshot.rows_written == 1,
                        detail="Stage-C SQLite row",
                    )

                    assert engine.mheard_db is not None
                    heard = engine.mheard_db.get("KJ6YWD-10")
                    assert heard is not None
                    self.assertEqual(heard.source, "KJ6YWD-10")
                    self.assertEqual(heard.heard_count, 1)
                    self.assertEqual(heard.last_destination, "YWDB")
                    self.assertEqual(heard.last_path, ("YWDNOD",))
                    self.assertIn("STAGE C OBSERVABILITY", heard.last_line)

                    diagnostics = engine.diagnostics_snapshot()
                    self.assertTrue(diagnostics.healthy, diagnostics.problems)
                    self.assertEqual(diagnostics.problems, ())
                    assert diagnostics.sqlite_log is not None
                    assert diagnostics.mheard is not None
                    self.assertEqual(diagnostics.sqlite_log["rows_written"], 1)
                    self.assertEqual(diagnostics.mheard["station_count"], 1)
                    self.assertEqual(diagnostics.mheard["frame_count"], 1)
                    self.assertIsNone(diagnostics.retention_plan)

                    # Stage C observes the same safe Stage-B ingress: DATA is
                    # still rejected immediately when product TX is disabled.
                    client.sendall(encode(body("STAGE C TX MUST REJECT"), command=DATA))
                    assert engine.session is not None
                    assert engine.admission is not None
                    wait_until(
                        lambda: engine.session.counters.kiss_data_tx_rejected == 1,
                        detail="Stage-C RX-only DATA rejection",
                    )
                    self.assertEqual(engine.admission.snapshot.queue_depth, 0)
                    self.assertEqual(created[0].tx_accept_count, 0)
                    engine.check_health()
            finally:
                monitor.close()
                engine.stop()

            self.assertTrue(database.exists())
            self.assertEqual(created[0].tx_accept_count, 0)
            self.assertEqual(created[0].rx_start_count, 1)
            self.assertEqual(created[0].rx_stop_count, 1)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)

    def test_monitor_without_logging_creates_no_database_or_mheard_writer(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            database = Path(td) / "must-not-exist.sqlite3"
            path = write_stage_c_config(
                td,
                database=None,
                monitor_enabled=True,
                log_frames=False,
                kiss_enabled=False,
            )
            config = load_product_packet_engine_config(path)
            engine = ProductPacketEngine(config, transport_factory=factory)
            engine.start()
            monitor = engine.open_monitor()
            try:
                inbound = body("MONITOR ONLY")
                created[0].inject_rx_packed(rx_capture(inbound))
                record = monitor.get(timeout=4.0)
                self.assertEqual(record.frame_no_fcs, inbound)
                self.assertFalse(database.exists())
                self.assertIsNone(engine.mheard_db)
                diagnostics = engine.diagnostics_snapshot()
                self.assertTrue(diagnostics.healthy, diagnostics.problems)
                self.assertIsNone(diagnostics.sqlite_log)
                self.assertIsNone(diagnostics.mheard)
                self.assertIsNone(diagnostics.retention_plan)
                engine.check_health()
            finally:
                monitor.close()
                engine.stop()

        self.assertEqual(created[0].tx_accept_count, 0)

    def test_logger_startup_failure_releases_single_modem_owner(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            missing_parent = Path(td) / "missing" / "frames.sqlite3"
            path = write_stage_c_config(
                td,
                database=missing_parent,
                monitor_enabled=True,
                log_frames=True,
                kiss_enabled=False,
            )
            config = load_product_packet_engine_config(path)
            engine = ProductPacketEngine(config, transport_factory=factory)
            with self.assertRaises(RuntimeError):
                engine.start()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].tx_accept_count, 0)
        self.assertEqual(created[0].rx_start_count, 1)
        self.assertEqual(created[0].rx_stop_count, 1)
        self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
        self.assertTrue(all(tid == created[0].owner_thread_id for tid in created[0].call_thread_ids))


if __name__ == "__main__":
    unittest.main(verbosity=2)
