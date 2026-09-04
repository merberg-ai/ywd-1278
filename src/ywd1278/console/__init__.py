"""Local classic-style TNC console primitives for YWD-1278."""

from .local import (
    MAX_COMMAND_CHARS,
    MAX_MHEARD_LIMIT,
    CommandResult,
    LocalTNCCommandShell,
    run_local_console,
)

__all__ = [
    "MAX_COMMAND_CHARS",
    "MAX_MHEARD_LIMIT",
    "CommandResult",
    "LocalTNCCommandShell",
    "run_local_console",
]
