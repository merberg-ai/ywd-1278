#!/usr/bin/env python3
"""0E-P1 local classic-style TNC command shell regression tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ywd1278.console.local import (  # noqa: E402
    MAX_COMMAND_CHARS,
    LocalTNCCommandShell,
    run_local_console,
)
from ywd1278.monitor.diagnostics import DiagnosticsSnapshot  # noqa: E402
from ywd1278.monitor.mheard import MHeardDatabase  # noqa: E402
from ywd1278.monitor.policy import MonitorPolicyState  # noqa: E402
from ywd1278.monitor.sqlite_log import _prepare_schema  # noqa: E402


class FakeDiagnostics:
    def __init__(self, snapshot: DiagnosticsSnapshot) -> None:
        self._snapshot = snapshot
        self.calls = 0

    def snapshot(self) -> DiagnosticsSnapshot:
        self.calls += 1
        return self._snapshot


class LocalTNCCommandShellTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = str(Path(directory) / "frames.sqlite3")
        connection = sqlite3.connect(path)
        _prepare_schema(connection)
        rows = (
            (100, 1, 0, "KJ6YWD", "JIM", "[]", "U", "UI", 0, None, None, 240, b"ONE", b"a", "KJ6YWD>JIM:ONE"),
            (200, 2, 0, "KJ6YWD-9", "APRS", '["WIDE1-1"]', "U", "UI", 0, None, None, 240, b"TWO", b"b", "KJ6YWD-9>APRS,WIDE1-1:TWO"),
            (300, 3, 0, "KJ6YWD", "JIM", "[]", "U", "UI", 0, None, None, 240, b"THREE", b"c", "KJ6YWD>JIM:THREE"),
        )
        connection.executemany(
            "INSERT INTO frames (observed_at_ns,monitor_sequence,history_replay,source,destination,path_json,frame_class,frame_type,poll_final,ns,nr,pid,info,frame_no_fcs,line) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
        connection.close()
        return path

    @staticmethod
    def _snapshot(*, healthy: bool = True) -> DiagnosticsSnapshot:
        return DiagnosticsSnapshot(
            runtime={"running": True, "decoded_rx_frames": 7},
            backend=None,
            parameters={"generation": 5, "txdelay": 30},
            control=None,
            ingress=None,
            queue={"tx_queue_depth": 0},
            connections=None,
            sqlite_log=None,
            mheard={"station_count": 2, "frame_count": 3, "latest_heard_ns": 300},
            retention_plan={"enabled": False, "eligible_rows": 0},
            healthy=healthy,
            problems=() if healthy else ("subscriber-drops",),
        )

    def test_help_version_case_and_blank_command(self):
        shell = LocalTNCCommandShell(version="test-version")
        self.assertEqual(shell.execute("\n").lines, ())
        self.assertEqual(shell.execute("version").lines, ("YWD-1278 test-version",))
        help_lines = shell.execute(" ? ").lines
        self.assertTrue(any(line.startswith("STATUS") for line in help_lines))
        self.assertTrue(any(line.startswith("MHEARD") for line in help_lines))
        self.assertTrue(any(line.startswith("QUIT") for line in help_lines))

    def test_status_and_health_render_only_supplied_snapshot(self):
        diagnostics = FakeDiagnostics(self._snapshot())
        shell = LocalTNCCommandShell(diagnostics=diagnostics)

        status = shell.execute("STATUS")
        self.assertEqual(status.lines[0], "STATUS OK")
        self.assertEqual(status.lines[1], "SOURCES 5/10")
        self.assertEqual(status.lines[2], "PROBLEMS NONE")
        self.assertIn("RUNTIME decoded_rx_frames=7 running=true", status.lines)
        self.assertIn("BACKEND UNAVAILABLE", status.lines)
        self.assertIn("MHEARD frame_count=3 latest_heard_ns=300 station_count=2", status.lines)

        health = shell.execute("HEALTH")
        self.assertEqual(
            health.lines,
            ("HEALTH OK", "PROBLEMS NONE", "SOURCES 5/10"),
        )
        self.assertEqual(diagnostics.calls, 2)

    def test_unhealthy_snapshot_preserves_ordered_problem_names(self):
        shell = LocalTNCCommandShell(diagnostics=FakeDiagnostics(self._snapshot(healthy=False)))
        self.assertEqual(
            shell.execute("HEALTH").lines,
            ("HEALTH FAIL", "PROBLEMS subscriber-drops", "SOURCES 5/10"),
        )

    def test_absent_diagnostics_are_explicitly_unavailable(self):
        shell = LocalTNCCommandShell()
        self.assertEqual(shell.execute("STATUS").lines, ("STATUS UNAVAILABLE",))
        self.assertEqual(shell.execute("HEALTH").lines, ("HEALTH UNAVAILABLE",))

    def test_monitor_controls_bind_only_to_frozen_policy_state(self):
        policy = MonitorPolicyState()
        shell = LocalTNCCommandShell(monitor_policy=policy)

        self.assertEqual(shell.execute("MCOM").lines, ("MCOM OFF",))
        self.assertEqual(shell.execute("MCON").lines, ("MCON OFF",))
        self.assertEqual(shell.execute("MRPT").lines, ("MRPT ON",))
        self.assertEqual(policy.snapshot.generation, 0)

        self.assertEqual(
            shell.execute("mcom on").lines,
            ("MCOM ON", "MONITOR_GENERATION 1"),
        )
        self.assertEqual(
            shell.execute("mrpt off").lines,
            ("MRPT OFF", "MONITOR_GENERATION 2"),
        )
        before = policy.snapshot
        self.assertEqual(
            shell.execute("MCON MAYBE").lines,
            ("ERROR MCON expects ON or OFF",),
        )
        self.assertEqual(policy.snapshot, before)

    def test_mheard_uses_read_only_qualified_database_view(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._database(td)
            shell = LocalTNCCommandShell(mheard_db=MHeardDatabase(path))
            rows = shell.execute("MHEARD").lines
            self.assertEqual(rows[0], "MHEARD 2")
            self.assertEqual(
                rows[1],
                "KJ6YWD COUNT=2 LAST_NS=300 DEST=JIM VIA=DIRECT",
            )
            self.assertEqual(
                rows[2],
                "KJ6YWD-9 COUNT=1 LAST_NS=200 DEST=APRS VIA=WIDE1-1",
            )
            self.assertEqual(shell.execute("MHEARD 1").lines[0], "MHEARD 1")
            self.assertEqual(
                shell.execute("MHEARD 0").lines,
                ("ERROR MHEARD limit must be 1..100",),
            )
            self.assertEqual(
                shell.execute("MHEARD nope").lines,
                ("ERROR MHEARD limit must be an integer",),
            )

    def test_unknown_and_future_tx_commands_fail_closed(self):
        diagnostics = FakeDiagnostics(self._snapshot())
        shell = LocalTNCCommandShell(diagnostics=diagnostics)
        for text in (
            "CONNECT KJ6YWD",
            "CONVERSE",
            "UNPROTO APRS",
            "BEACON EVERY 10",
            "TX hello",
            "SEND hello",
            "TRANSMIT hello",
            "KISS ON",
            "!ls",
            "SHELL",
        ):
            result = shell.execute(text)
            self.assertEqual(len(result.lines), 1, text)
            self.assertTrue(result.lines[0].startswith("ERROR UNKNOWN COMMAND "), text)
        self.assertEqual(diagnostics.calls, 0)

    def test_command_length_nul_and_extra_arguments_fail_closed(self):
        shell = LocalTNCCommandShell()
        self.assertEqual(
            shell.execute("A" * (MAX_COMMAND_CHARS + 1)).lines,
            (f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters",),
        )
        self.assertEqual(
            shell.execute("VERSION\x00oops").lines,
            ("ERROR COMMAND contains NUL",),
        )
        self.assertEqual(
            shell.execute("STATUS extra").lines,
            ("ERROR STATUS takes no arguments",),
        )
        self.assertEqual(
            shell.execute("MCOM ON extra").lines,
            ("ERROR MCOM expects ON or OFF",),
        )

    def test_stdio_loop_uses_classic_cmd_prompt_and_stops_on_quit(self):
        shell = LocalTNCCommandShell(version="loop-test")
        inp = StringIO("VERSION\nQUIT\nVERSION\n")
        out = StringIO()
        rc = run_local_console(shell, input_stream=inp, output_stream=out)
        text = out.getvalue()

        self.assertEqual(rc, 0)
        self.assertIn("YWD-1278 loop-test LOCAL TNC CONSOLE\n", text)
        self.assertIn("cmd:YWD-1278 loop-test\n", text)
        self.assertIn("cmd:BYE\n", text)
        self.assertEqual(text.count("YWD-1278 loop-test\n"), 1)
        self.assertEqual(text.count("cmd:"), 2)

    def test_stdio_loop_discards_oversized_line_before_next_command(self):
        shell = LocalTNCCommandShell(version="bounded")
        inp = StringIO("X" * 600 + "\nVERSION\nEXIT\n")
        out = StringIO()
        rc = run_local_console(shell, input_stream=inp, output_stream=out)
        text = out.getvalue()

        self.assertEqual(rc, 0)
        self.assertIn(f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters\n", text)
        self.assertIn("YWD-1278 bounded\n", text)
        self.assertIn("BYE\n", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
