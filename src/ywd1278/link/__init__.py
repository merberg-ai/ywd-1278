"""Host-side native AX.25 connected-mode primitives."""

from .modulo8 import (
    LinkAction,
    LinkEventResult,
    LinkSnapshot,
    LinkState,
    Modulo8Link,
    build_unnumbered_frame,
    sequence_distance,
    sequence_next,
)
from .data_link import (
    DataLinkAction,
    DataLinkResult,
    DataLinkSnapshot,
    Modulo8DataLink,
    build_i_frame,
    build_s_frame,
)
from .timed_link import (
    LinkTimerConfig,
    LinkTimerSnapshot,
    TimedLinkResult,
    TimedModulo8DataLink,
)
from .terminal_session import (
    ConnectedTerminalResult,
    ConnectedTerminalSession,
    ConnectedTerminalSnapshot,
    TerminalMode,
)

__all__ = [
    "LinkAction",
    "LinkEventResult",
    "LinkSnapshot",
    "LinkState",
    "Modulo8Link",
    "build_unnumbered_frame",
    "sequence_distance",
    "sequence_next",
    "DataLinkAction",
    "DataLinkResult",
    "DataLinkSnapshot",
    "Modulo8DataLink",
    "build_i_frame",
    "build_s_frame",
    "LinkTimerConfig",
    "LinkTimerSnapshot",
    "TimedLinkResult",
    "TimedModulo8DataLink",
    "ConnectedTerminalResult",
    "ConnectedTerminalSession",
    "ConnectedTerminalSnapshot",
    "TerminalMode",
]
