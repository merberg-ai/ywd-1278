"""YWD-1278 KISS framing and RX-only TCP service primitives."""

from .framing import DATA, FEND, FESC, TFEND, TFESC, KISSMessage, KISSStreamDecoder, decode, encode
from .server import BackendSnapshot, PacketEvent, RXOnlyBackend, ThreadingKISSServer, start_server_thread, stop_server_thread

__all__ = [
    "DATA",
    "FEND",
    "FESC",
    "TFEND",
    "TFESC",
    "KISSMessage",
    "KISSStreamDecoder",
    "decode",
    "encode",
    "BackendSnapshot",
    "PacketEvent",
    "RXOnlyBackend",
    "ThreadingKISSServer",
    "start_server_thread",
    "stop_server_thread",
]
