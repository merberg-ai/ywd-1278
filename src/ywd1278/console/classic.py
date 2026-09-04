"""Safe TNC2/MFJ-style vocabulary adapter for the 0E-P5 classic console.

0E-P5 deliberately leaves the frozen 0E-P1 parser and the qualified P2/P3/P4
transport layers unchanged. ``ClassicTNCCommandShell`` subclasses the frozen
``LocalTNCCommandShell`` and adds only explicit, bounded compatibility aliases,
a safe DISPLAY view of monitor parameters, and deterministic recognition of
legacy commands that are deferred to later phases.

No legacy command in this module can open a modem, KISS session, hardware
serial device, network listener, database writer, GPIO path, or RF/TX path.
There is intentionally no generic command-abbreviation engine: ambiguous short
forms fail closed instead of guessing an operator's intent.
"""

from __future__ import annotations

import argparse
from typing import Any

from ywd1278 import __version__
from ywd1278.console.local import (
    MAX_COMMAND_CHARS,
    CommandResult,
    LocalTNCCommandShell,
    run_local_console,
)
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


_SAFE_ALIASES = {
    "DISP": "DISPLAY",
    "MH": "MHEARD",
    "VER": "VERSION",
    "STAT": "STATUS",
    "HEAL": "HEALTH",
}

# Recognized TNC2/MFJ vocabulary that must remain non-operational in 0E-P5.
# The value is the phase or boundary that owns eventual implementation.
_DEFERRED_COMMANDS = {
    # 0F — UI/unproto/converse/beacon transmit behavior.
    "UNPROTO": "0F",
    "CONVERSE": "0F",
    "BEACON": "0F",
    "BTEXT": "0F",
    "ID": "0F",
    # 0G — native connected-mode AX.25 behavior.
    "CONNECT": "0G",
    "DISCONNECT": "0G",
    "RECONNECT": "0G",
    "CSTATUS": "0G",
    "CONMODE": "0G",
    "CONOK": "0G",
    "CONPERM": "0G",
    "MAXFRAME": "0G",
    "PACLEN": "0G",
    "RETRY": "0G",
    "TRIES": "0G",
    "FRACK": "0G",
    "RESPTIME": "0G",
    # Later product/runtime configuration surfaces.  These are intentionally
    # recognized so a classic-TNC operator gets a deterministic answer, but
    # they do not alter the already-qualified packet runtime in this phase.
    "MYCALL": "LATER-CONFIG",
    "MYALIAS": "LATER-CONFIG",
    "DIGIPEAT": "LATER-CONFIG",
    "MONITOR": "LATER-MONITOR-GATE",
    "MALL": "LATER-MONITOR-GATE",
    "PASSALL": "LATER-RX-POLICY",
    "TXDELAY": "LATER-TNC-PARAMETER-CONTROL",
    "PERSIST": "LATER-TNC-PARAMETER-CONTROL",
    "SLOTTIME": "LATER-TNC-PARAMETER-CONTROL",
    "FULLDUP": "LATER-TNC-PARAMETER-CONTROL",
    "FULLDUPLEX": "LATER-TNC-PARAMETER-CONTROL",
    "XMITOK": "LATER-TX-ENABLE-CONTROL",
    "KISS": "LATER-KISS-MODE-CONTROL",
    "TX": "LATER-TX-COMMAND",
    "SEND": "LATER-TX-COMMAND",
    "TRANSMIT": "LATER-TX-COMMAND",
}

_DISABLED_COMMANDS = {
    "MHCLEAR": "read-only MHEARD boundary",
    "RESET": "reset control disabled",
    "RESTART": "restart control disabled",
    "SHELL": "shell escape disabled",
}

_CLASSIC_HELP_LINES = (
    "DISPLAY [MONITOR]    show supported classic monitor parameters",
    "DISP [MONITOR]       safe alias for DISPLAY",
    "MH [1-100]           classic alias for MHEARD",
    "VER                  safe alias for VERSION",
    "STAT                 safe alias for STATUS",
    "HEAL                 safe alias for HEALTH",
    "NOTE                 ambiguous abbreviations are not accepted",
    "NOTE                 TX/link/config legacy commands remain deferred",
)


class ClassicTNCCommandShell(LocalTNCCommandShell):
    """Frozen P1 shell plus a narrow, fail-closed classic vocabulary adapter."""

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")
        if "\x00" in line:
            return super().execute(line)

        normalized = line.strip(" \t\r\n")
        if len(normalized) > MAX_COMMAND_CHARS or not normalized:
            return super().execute(line)

        parts = normalized.split()
        command = parts[0].upper()
        args = parts[1:]

        if command in ("HELP", "?"):
            if args:
                return super().execute(line)
            base = super().execute("HELP")
            return CommandResult(base.lines + _CLASSIC_HELP_LINES)

        command = _SAFE_ALIASES.get(command, command)

        if command == "DISPLAY":
            return self._display(args)

        deferred = _DEFERRED_COMMANDS.get(command)
        if deferred is not None:
            return CommandResult(
                (f"ERROR {command} NOT AVAILABLE IN 0E-P5; OWNER={deferred}",)
            )

        disabled = _DISABLED_COMMANDS.get(command)
        if disabled is not None:
            return CommandResult((f"ERROR {command} DISABLED; {disabled}",))

        if command != parts[0].upper():
            rebuilt = " ".join((command, *args))
            return super().execute(rebuilt)
        return super().execute(line)

    def _display(self, args: list[str]) -> CommandResult:
        if len(args) > 1:
            return CommandResult(("ERROR DISPLAY expects at most MONITOR",))
        if args and args[0].upper() != "MONITOR":
            return CommandResult(("ERROR DISPLAY supports MONITOR only in 0E-P5",))

        lines = ["DISPLAY MONITOR"]
        for command in ("MCOM", "MCON", "MRPT"):
            result = super().execute(command)
            if not result.lines:
                return CommandResult((f"ERROR DISPLAY failed to query {command}",))
            lines.extend(result.lines)
        return CommandResult(tuple(lines))


def make_classic_shell(
    *,
    database_path: str | None = None,
    diagnostics: Any = None,
    monitor_policy: MonitorPolicyState | None = None,
    mheard_db: Any = None,
    version: str = __version__,
) -> ClassicTNCCommandShell:
    """Construct one P5 shell without creating any transport or TX capability."""
    if database_path is not None and (diagnostics is not None or mheard_db is not None):
        raise ValueError("database_path cannot be combined with injected diagnostics/mheard_db")
    if database_path is not None:
        mheard_db = MHeardDatabase(database_path)
        diagnostics = DiagnosticsStatus(mheard_db=mheard_db)
    return ClassicTNCCommandShell(
        diagnostics=diagnostics,
        monitor_policy=monitor_policy or MonitorPolicyState(),
        mheard_db=mheard_db,
        version=version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m ywd1278.console.classic",
        description="YWD-1278 0E-P5 safe TNC2/MFJ-style local command vocabulary",
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        help="optional qualified 0D-P3 SQLite frame log for read-only MHEARD/status",
    )
    args = parser.parse_args(argv)
    shell = make_classic_shell(database_path=args.database)
    return run_local_console(shell)


if __name__ == "__main__":
    raise SystemExit(main())
