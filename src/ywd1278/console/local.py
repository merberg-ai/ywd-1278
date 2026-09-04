"""Host-only local classic-style TNC command shell for 0E-P1.

This module deliberately provides only a local stdin/stdout command surface over
already-qualified monitor/diagnostics objects. It does not open a network
listener, PTY, serial port, modem owner, KISS session, database writer, or TX
path. Commands are exact-token and fail closed; there is no shell escape,
command abbreviation, dynamic loading, or arbitrary code execution.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from typing import Any, TextIO

from ywd1278 import __version__
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


MAX_COMMAND_CHARS = 256
MAX_MHEARD_LIMIT = 100
DEFAULT_MHEARD_LIMIT = 20
PROMPT = "cmd:"

_COMPONENTS = (
    "runtime",
    "backend",
    "parameters",
    "control",
    "ingress",
    "queue",
    "connections",
    "sqlite_log",
    "mheard",
    "retention_plan",
)

_HELP_LINES = (
    "HELP                 show this command list",
    "VERSION              show YWD-1278 version",
    "STATUS               show one-shot diagnostics/status",
    "HEALTH               show known health problems",
    "MHEARD [1-100]       list recently heard stations",
    "MCOM [ON|OFF]        query/set protocol-control monitoring",
    "MCON [ON|OFF]        query/set connected-context monitoring",
    "MRPT [ON|OFF]        query/set digipeater-path display",
    "QUIT | EXIT          leave the local console",
)


@dataclass(frozen=True)
class CommandResult:
    lines: tuple[str, ...] = ()
    close: bool = False


def _clean_text(value: Any, *, limit: int = 160) -> str:
    if value is None:
        text = "-"
    elif type(value) is bool:
        text = "true" if value else "false"
    else:
        text = str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text


def _render_mapping(name: str, value: dict[str, Any] | None) -> str:
    label = name.upper()
    if value is None:
        return f"{label} UNAVAILABLE"
    if not value:
        return f"{label} EMPTY"
    fields = " ".join(
        f"{key}={_clean_text(value[key])}" for key in sorted(value)
    )
    return f"{label} {fields}"


def _source_count(snapshot: Any) -> int:
    return sum(getattr(snapshot, name, None) is not None for name in _COMPONENTS)


def _error(command: str, exc: Exception) -> CommandResult:
    message = _clean_text(str(exc), limit=120)
    if message == "-":
        message = type(exc).__name__
    return CommandResult((f"ERROR {command} {type(exc).__name__}: {message}",))


class LocalTNCCommandShell:
    """Deterministic command processor for one local terminal session."""

    def __init__(
        self,
        *,
        diagnostics: Any = None,
        monitor_policy: MonitorPolicyState | None = None,
        mheard_db: Any = None,
        version: str = __version__,
    ) -> None:
        if diagnostics is not None and not callable(getattr(diagnostics, "snapshot", None)):
            raise TypeError("diagnostics must provide snapshot()")
        if monitor_policy is not None and not isinstance(monitor_policy, MonitorPolicyState):
            raise TypeError("monitor_policy must be MonitorPolicyState or None")
        if mheard_db is not None and not callable(getattr(mheard_db, "list", None)):
            raise TypeError("mheard_db must provide list()")
        if not isinstance(version, str) or not version:
            raise ValueError("version must be a non-empty string")

        self._diagnostics = diagnostics
        self._monitor_policy = monitor_policy or MonitorPolicyState()
        self._mheard_db = mheard_db
        self._version = version

    @property
    def monitor_policy(self) -> MonitorPolicyState:
        return self._monitor_policy

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        if "\x00" in line:
            return CommandResult(("ERROR COMMAND contains NUL",))

        normalized = line.strip(" \t\r\n")
        if len(normalized) > MAX_COMMAND_CHARS:
            return CommandResult(
                (f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters",)
            )
        if not normalized:
            return CommandResult()

        parts = normalized.split()
        command = parts[0].upper()
        args = parts[1:]

        if command in ("HELP", "?"):
            if args:
                return CommandResult(("ERROR HELP takes no arguments",))
            return CommandResult(_HELP_LINES)
        if command == "VERSION":
            if args:
                return CommandResult(("ERROR VERSION takes no arguments",))
            return CommandResult((f"YWD-1278 {self._version}",))
        if command == "STATUS":
            return self._status(args)
        if command == "HEALTH":
            return self._health(args)
        if command == "MHEARD":
            return self._mheard(args)
        if command in ("MCOM", "MCON", "MRPT"):
            return self._monitor_control(command, args)
        if command in ("QUIT", "EXIT"):
            if args:
                return CommandResult((f"ERROR {command} takes no arguments",))
            return CommandResult(("BYE",), close=True)

        return CommandResult((f"ERROR UNKNOWN COMMAND {command}",))

    def _snapshot(self, command: str) -> tuple[Any | None, CommandResult | None]:
        if self._diagnostics is None:
            return None, CommandResult((f"{command} UNAVAILABLE",))
        try:
            return self._diagnostics.snapshot(), None
        except Exception as exc:
            return None, _error(command, exc)

    def _status(self, args: list[str]) -> CommandResult:
        if args:
            return CommandResult(("ERROR STATUS takes no arguments",))
        snapshot, error = self._snapshot("STATUS")
        if error is not None:
            return error
        assert snapshot is not None

        healthy = bool(getattr(snapshot, "healthy", False))
        problems = tuple(getattr(snapshot, "problems", ()))
        source_count = _source_count(snapshot)
        lines = [
            f"STATUS {'OK' if healthy else 'FAIL'}",
            f"SOURCES {source_count}/{len(_COMPONENTS)}",
            "PROBLEMS " + (",".join(_clean_text(item) for item in problems) if problems else "NONE"),
        ]
        for name in _COMPONENTS:
            value = getattr(snapshot, name, None)
            if value is not None and not isinstance(value, dict):
                return CommandResult((f"ERROR STATUS invalid {name} snapshot",))
            lines.append(_render_mapping(name, value))
        return CommandResult(tuple(lines))

    def _health(self, args: list[str]) -> CommandResult:
        if args:
            return CommandResult(("ERROR HEALTH takes no arguments",))
        snapshot, error = self._snapshot("HEALTH")
        if error is not None:
            return error
        assert snapshot is not None

        healthy = bool(getattr(snapshot, "healthy", False))
        problems = tuple(getattr(snapshot, "problems", ()))
        return CommandResult(
            (
                f"HEALTH {'OK' if healthy else 'FAIL'}",
                "PROBLEMS " + (",".join(_clean_text(item) for item in problems) if problems else "NONE"),
                f"SOURCES {_source_count(snapshot)}/{len(_COMPONENTS)}",
            )
        )

    def _mheard(self, args: list[str]) -> CommandResult:
        if self._mheard_db is None:
            return CommandResult(("MHEARD UNAVAILABLE",))
        if len(args) > 1:
            return CommandResult(("ERROR MHEARD expects at most one limit",))

        limit = DEFAULT_MHEARD_LIMIT
        if args:
            try:
                limit = int(args[0], 10)
            except ValueError:
                return CommandResult(("ERROR MHEARD limit must be an integer",))
            if not 1 <= limit <= MAX_MHEARD_LIMIT:
                return CommandResult(
                    (f"ERROR MHEARD limit must be 1..{MAX_MHEARD_LIMIT}",)
                )

        try:
            entries = self._mheard_db.list(limit=limit)
        except Exception as exc:
            return _error("MHEARD", exc)

        lines = [f"MHEARD {len(entries)}"]
        for entry in entries:
            path = ",".join(entry.last_path) if entry.last_path else "DIRECT"
            lines.append(
                f"{_clean_text(entry.source, limit=32)} "
                f"COUNT={int(entry.heard_count)} "
                f"LAST_NS={int(entry.last_heard_ns)} "
                f"DEST={_clean_text(entry.last_destination, limit=32)} "
                f"VIA={_clean_text(path, limit=80)}"
            )
        return CommandResult(tuple(lines))

    def _monitor_control(self, command: str, args: list[str]) -> CommandResult:
        if len(args) > 1:
            return CommandResult((f"ERROR {command} expects ON or OFF",))

        attribute = command.lower()
        if not args:
            value = bool(getattr(self._monitor_policy.snapshot, attribute))
            return CommandResult((f"{command} {'ON' if value else 'OFF'}",))

        token = args[0].upper()
        if token not in ("ON", "OFF"):
            return CommandResult((f"ERROR {command} expects ON or OFF",))
        value = token == "ON"
        setter = getattr(self._monitor_policy, f"set_{attribute}")
        snapshot = setter(value)
        effective = bool(getattr(snapshot, attribute))
        return CommandResult(
            (
                f"{command} {'ON' if effective else 'OFF'}",
                f"MONITOR_GENERATION {int(snapshot.generation)}",
            )
        )


def run_local_console(
    shell: LocalTNCCommandShell,
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    if not isinstance(shell, LocalTNCCommandShell):
        raise TypeError("shell must be LocalTNCCommandShell")

    output_stream.write(f"YWD-1278 {shell._version} LOCAL TNC CONSOLE\n")
    output_stream.write("0E-P1 host-only command mode; type HELP for commands.\n")
    output_stream.flush()

    while True:
        output_stream.write(PROMPT)
        output_stream.flush()
        raw = input_stream.readline(MAX_COMMAND_CHARS + 2)
        if raw == "":
            output_stream.write("\n")
            output_stream.flush()
            return 0

        if len(raw) > MAX_COMMAND_CHARS and not raw.endswith("\n"):
            while True:
                tail = input_stream.readline(MAX_COMMAND_CHARS + 2)
                if tail == "" or tail.endswith("\n"):
                    break
            result = CommandResult(
                (f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters",)
            )
        else:
            result = shell.execute(raw)

        for line in result.lines:
            output_stream.write(line + "\n")
        output_stream.flush()
        if result.close:
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ywd1278-console",
        description="YWD-1278 local classic-style TNC command shell",
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        help="optional qualified 0D-P3 SQLite frame log for read-only MHEARD/status",
    )
    args = parser.parse_args(argv)

    mheard = None
    diagnostics = None
    if args.database:
        mheard = MHeardDatabase(args.database)
        diagnostics = DiagnosticsStatus(mheard_db=mheard)

    shell = LocalTNCCommandShell(
        diagnostics=diagnostics,
        monitor_policy=MonitorPolicyState(),
        mheard_db=mheard,
    )
    return run_local_console(shell)


if __name__ == "__main__":
    raise SystemExit(main())
