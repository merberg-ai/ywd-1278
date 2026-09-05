"""0H-P1 bounded packet-node command session with no runtime ownership."""

from __future__ import annotations

from dataclasses import dataclass

from ywd1278 import __version__
from ywd1278.ax25 import Address


MAX_NODE_COMMAND_BYTES = 128
MAX_NODE_BUFFER_BYTES = 256


@dataclass(frozen=True)
class NodeCommandSnapshot:
    callsign: str
    alias: str
    buffered_bytes: int
    commands: int
    rejected: int
    close_requested: bool


@dataclass(frozen=True)
class NodeCommandResult:
    accepted: bool
    reason: str
    responses: tuple[bytes, ...] = ()
    close_requested: bool = False


class NodeCommandSession:
    """Consume CR/LF-delimited node commands and return inert response bytes."""

    def __init__(self, *, callsign: Address, alias: str = "YWDNOD") -> None:
        if not isinstance(callsign, Address):
            raise TypeError("callsign must be an AX.25 Address")
        normalized_alias = str(alias).strip().upper()
        if not 1 <= len(normalized_alias) <= 6 or not normalized_alias.isalnum():
            raise ValueError("alias must be 1..6 alphanumeric ASCII characters")
        if not normalized_alias.isascii():
            raise ValueError("alias must be ASCII")
        self._callsign = Address(callsign.callsign, callsign.ssid)
        self._alias = normalized_alias
        self._buffer = bytearray()
        self._commands = 0
        self._rejected = 0
        self._close_requested = False

    @property
    def snapshot(self) -> NodeCommandSnapshot:
        return NodeCommandSnapshot(
            callsign=str(self._callsign), alias=self._alias,
            buffered_bytes=len(self._buffer), commands=self._commands,
            rejected=self._rejected, close_requested=self._close_requested,
        )

    def banner(self) -> tuple[bytes, ...]:
        return (
            f"YWD-1278 NODE {self._alias}:{self._callsign}\r".encode("ascii"),
            b"Type HELP for commands\r",
        )

    def feed(self, information: bytes) -> NodeCommandResult:
        if not isinstance(information, bytes):
            raise TypeError("information must be bytes")
        if self._close_requested:
            return self._reject("node session is closed", close=True)
        if len(self._buffer) + len(information) > MAX_NODE_BUFFER_BYTES:
            self._buffer.clear()
            return self._reject("node command buffer overflow")
        self._buffer.extend(information)
        responses: list[bytes] = []
        processed = 0
        all_accepted = True
        while True:
            separator = next(
                (index for index, value in enumerate(self._buffer) if value in (10, 13)),
                None,
            )
            if separator is None:
                break
            raw = bytes(self._buffer[:separator])
            end = separator + 1
            while end < len(self._buffer) and self._buffer[end] in (10, 13):
                end += 1
            del self._buffer[:end]
            if not raw:
                continue
            processed += 1
            result = self._execute(raw)
            all_accepted = all_accepted and result.accepted
            responses.extend(result.responses)
            if result.close_requested:
                self._buffer.clear()
                break
        if not processed:
            return NodeCommandResult(True, "partial command buffered")
        return NodeCommandResult(
            all_accepted, f"processed {processed} command(s)", tuple(responses), self._close_requested
        )

    def _execute(self, raw: bytes) -> NodeCommandResult:
        self._commands += 1
        if len(raw) > MAX_NODE_COMMAND_BYTES:
            return self._reject("node command exceeds 128 bytes")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            return self._reject("node command must be ASCII")
        if any(ord(char) < 32 or ord(char) > 126 for char in text):
            return self._reject("node command must be printable ASCII")
        parts = text.strip().split()
        if not parts:
            return NodeCommandResult(True, "blank command")
        command = parts[0].upper()
        args = parts[1:]
        if command in ("HELP", "?") and not args:
            return self._ok(
                "HELP              show commands",
                "INFO              show node identity and scope",
                "VERSION           show software version",
                "BYE               close this node session",
            )
        if command == "INFO" and not args:
            return self._ok(
                f"NODE {self._alias}:{self._callsign}",
                "Native AX.25 connected service; mailbox and forwarding unavailable",
            )
        if command == "VERSION" and not args:
            return self._ok(f"YWD-1278 {__version__}")
        if command in ("B", "BYE", "QUIT") and not args:
            self._close_requested = True
            return NodeCommandResult(True, "node session close requested", (b"BYE\r",), True)
        return self._reject(f"unknown or invalid node command {command}")

    @staticmethod
    def _ok(*lines: str) -> NodeCommandResult:
        return NodeCommandResult(
            True, "node command accepted", tuple((line + "\r").encode("ascii") for line in lines)
        )

    def _reject(self, reason: str, *, close: bool = False) -> NodeCommandResult:
        self._rejected += 1
        return NodeCommandResult(False, reason, (f"ERROR {reason}\r".encode("ascii"),), close)


__all__ = [
    "MAX_NODE_COMMAND_BYTES", "MAX_NODE_BUFFER_BYTES",
    "NodeCommandSnapshot", "NodeCommandResult", "NodeCommandSession",
]
