"""0I-P2 classic packet BBS command personality over the frozen P1 store.

This is a bounded line-oriented session adapter.  It owns no AX.25 link, modem,
KISS socket, scheduler, service lifecycle, or RF path.  Callers feed connected
information bytes and receive inert response actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from ywd1278.ax25 import Address
from ywd1278.node.persistent_mailbox import (
    MAX_BBS_BODY_BYTES,
    MAX_BBS_SUBJECT_BYTES,
    MailboxMessageType,
    PersistentMailboxAuthorizationError,
    PersistentMailboxDuplicateBidError,
    PersistentMailboxError,
    PersistentMailboxListEntry,
    PersistentMailboxQuotaError,
    PersistentMailboxStore,
)


MAX_BBS_COMMAND_BYTES = 256
MAX_BBS_INPUT_BUFFER_BYTES = 512
MIN_BBS_PACLEN = 32
MAX_BBS_PACLEN = 256
DEFAULT_BBS_LIST_LIMIT = 12


@dataclass(frozen=True)
class ClassicBBSAction:
    data: bytes
    close: bool = False


@dataclass(frozen=True)
class ClassicBBSResult:
    accepted: bool
    reason: str
    actions: tuple[ClassicBBSAction, ...] = ()
    close_requested: bool = False


@dataclass(frozen=True)
class ClassicBBSSnapshot:
    peer: str
    local: str
    buffered_bytes: int
    commands: int
    rejected: int
    composing: bool
    compose_bytes: int
    close_requested: bool


class _ComposeKind(Enum):
    PERSONAL = "PERSONAL"
    BULLETIN = "BULLETIN"


class _ComposeStage(Enum):
    TITLE = "TITLE"
    BODY = "BODY"


@dataclass
class _Composition:
    kind: _ComposeKind
    destination: str
    stage: _ComposeStage = _ComposeStage.TITLE
    subject: str = ""
    body: bytearray | None = None

    def __post_init__(self) -> None:
        if self.body is None:
            self.body = bytearray()


class ClassicBBSSession:
    """One classic BBS personality bound to the connected peer identity."""

    def __init__(
        self,
        *,
        local: Address,
        peer: Address,
        store: PersistentMailboxStore,
        paclen: int,
        now_ns: Callable[[], int],
        info: str = "YWD-1278 persistent packet BBS",
    ) -> None:
        if not isinstance(local, Address) or not isinstance(peer, Address):
            raise TypeError("local and peer must be AX.25 Address values")
        if not isinstance(store, PersistentMailboxStore):
            raise TypeError("store must be PersistentMailboxStore")
        if isinstance(paclen, bool) or not isinstance(paclen, int) or not MIN_BBS_PACLEN <= paclen <= MAX_BBS_PACLEN:
            raise ValueError(f"paclen must be an integer {MIN_BBS_PACLEN}..{MAX_BBS_PACLEN}")
        if not callable(now_ns):
            raise TypeError("now_ns must be callable")
        if not isinstance(info, str) or not info:
            raise ValueError("info must be a non-empty string")
        try:
            info.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("info must be ASCII") from exc
        self._local = Address(local.callsign, local.ssid)
        self._peer = Address(peer.callsign, peer.ssid)
        self._store = store
        self._paclen = paclen
        self._now_ns = now_ns
        self._info = info
        self._buffer = bytearray()
        self._commands = 0
        self._rejected = 0
        self._close_requested = False
        self._composition: _Composition | None = None

    @property
    def snapshot(self) -> ClassicBBSSnapshot:
        compose_bytes = 0
        if self._composition is not None and self._composition.body is not None:
            compose_bytes = len(self._composition.body)
        return ClassicBBSSnapshot(
            str(self._peer),
            str(self._local),
            len(self._buffer),
            self._commands,
            self._rejected,
            self._composition is not None,
            compose_bytes,
            self._close_requested,
        )

    def banner(self) -> tuple[ClassicBBSAction, ...]:
        try:
            counts = self._store.counts_for(self._peer)
            lines = (
                f"YWD BBS:{self._local}",
                f"Hello {self._peer.callsign} - {counts.new} new / {counts.visible} visible message(s)",
                "Type H for help",
            )
        except PersistentMailboxError as exc:
            lines = (f"YWD BBS:{self._local}", f"Mailbox unavailable: {exc}")
        return self._lines(*lines, prompt=True)

    def feed(self, information: bytes) -> ClassicBBSResult:
        if not isinstance(information, bytes):
            raise TypeError("information must be bytes")
        if self._close_requested:
            return self._reject("BBS session is closed", close=True)
        if len(self._buffer) + len(information) > MAX_BBS_INPUT_BUFFER_BYTES:
            self._buffer.clear()
            self._clear_composition()
            return self._reject("BBS input buffer overflow")
        self._buffer.extend(information)
        actions: list[ClassicBBSAction] = []
        accepted = True
        processed = 0
        while True:
            separator = next((i for i, value in enumerate(self._buffer) if value in (10, 13)), None)
            if separator is None:
                break
            raw = bytes(self._buffer[:separator])
            end = separator + 1
            while end < len(self._buffer) and self._buffer[end] in (10, 13):
                end += 1
            del self._buffer[:end]
            if not raw and self._composition is None:
                continue
            processed += 1
            result = self._execute_line(raw)
            accepted = accepted and result.accepted
            actions.extend(result.actions)
            if result.close_requested:
                self._buffer.clear()
                break
        if processed == 0:
            return ClassicBBSResult(True, "partial BBS line buffered")
        return ClassicBBSResult(
            accepted,
            f"processed {processed} BBS line(s)",
            tuple(actions),
            self._close_requested,
        )

    def _execute_line(self, raw: bytes) -> ClassicBBSResult:
        if len(raw) > MAX_BBS_COMMAND_BYTES:
            self._clear_composition()
            return self._reject(f"BBS line exceeds {MAX_BBS_COMMAND_BYTES} bytes")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            self._clear_composition()
            return self._reject("BBS line must be ASCII")
        if any(ord(char) < 32 or ord(char) > 126 for char in text):
            self._clear_composition()
            return self._reject("BBS line must contain printable ASCII")
        if self._composition is not None:
            return self._composition_line(raw, text)

        stripped = text.strip()
        if not stripped:
            return self._ok(prompt=True)
        self._commands += 1
        parts = stripped.split()
        command = parts[0].upper()
        args = parts[1:]

        if command in {"H", "HELP", "?"} and not args:
            return self._help()
        if command in {"I", "INFO"} and not args:
            return self._info_command()
        if command in {"B", "BYE"} and not args:
            self._close_requested = True
            return ClassicBBSResult(
                True,
                "BBS session close requested",
                self._lines("73 - disconnecting from YWD BBS", close=True),
                True,
            )
        if command in {"L", "LIST"}:
            return self._list_command(args, new_only=False, oldest_first=False, sent=False)
        if command == "LN":
            return self._list_command(args, new_only=True, oldest_first=False, sent=False)
        if command == "LR":
            return self._list_command(args, new_only=False, oldest_first=True, sent=False)
        if command == "LM":
            return self._list_command(args, new_only=False, oldest_first=False, sent=True)
        if command in {"R", "READ"}:
            return self._read_command(args)
        if command in {"K", "KILL"}:
            return self._kill_command(args)
        if command == "SP":
            return self._start_personal(args)
        if command == "SB":
            return self._start_bulletin(args)
        return self._reject("unknown BBS command; type H for help", prompt=True)

    def _help(self) -> ClassicBBSResult:
        return self._ok(
            "H or ?           Help",
            "L [n]            List visible messages (newest first)",
            "LN [n]           List new/unread messages",
            "LR [n]           List visible messages (oldest first)",
            "LM [n]           List messages sent by you",
            "R <n>            Read message n",
            "K <n>            Kill an owned message",
            "SP <call>        Send personal message",
            "SB <topic>       Send bulletin (example: SB ALL)",
            "I or INFO        BBS information",
            "B or BYE         Disconnect",
            "During compose: /EX saves, /ABORT cancels",
            prompt=True,
        )

    def _info_command(self) -> ClassicBBSResult:
        counts = self._store.counts_for(self._peer)
        return self._ok(
            self._info,
            f"BBS {self._local} - mailbox owner {self._peer.callsign}",
            f"Visible {counts.visible}; new {counts.new}; sent {counts.sent}",
            "Personal mail and local bulletins are available; forwarding is disabled",
            prompt=True,
        )

    def _list_command(
        self,
        args: list[str],
        *,
        new_only: bool,
        oldest_first: bool,
        sent: bool,
    ) -> ClassicBBSResult:
        if len(args) > 1:
            return self._reject("usage: L/LN/LR/LM [1..100]", prompt=True)
        try:
            limit = DEFAULT_BBS_LIST_LIMIT if not args else int(args[0], 10)
        except ValueError:
            return self._reject("list limit must be an integer", prompt=True)
        if not 1 <= limit <= 100:
            return self._reject("list limit must be 1..100", prompt=True)
        try:
            if sent:
                entries = self._store.list_sent(
                    self._peer, limit=limit, oldest_first=oldest_first
                )
            else:
                entries = self._store.list_visible(
                    self._peer,
                    limit=limit,
                    new_only=new_only,
                    oldest_first=oldest_first,
                )
        except (PersistentMailboxError, ValueError) as exc:
            return self._reject(f"mailbox unavailable: {exc}", prompt=True)
        if not entries:
            return self._ok("No messages", prompt=True)
        lines = ["Msg#  TS  Size  To/Topic      From    Subject"]
        lines.extend(self._format_list_entry(entry) for entry in entries)
        return self._ok(*lines, prompt=True)

    def _read_command(self, args: list[str]) -> ClassicBBSResult:
        if len(args) != 1:
            return self._reject("usage: R <message-number>", prompt=True)
        try:
            message_id = int(args[0], 10)
            now = self._clock()
            message = self._store.read_for(self._peer, message_id, read_at_ns=now)
        except (ValueError, PersistentMailboxError) as exc:
            return self._reject(f"message read failed: {exc}", prompt=True)
        if message is None:
            return self._reject("message not found or not visible to you", prompt=True)
        status = f"{message.message_type.value}R"
        bid = message.bid or "-"
        header = (
            f"From: {message.sender}",
            f"To: {message.recipient}",
            f"Type/Status: {status}",
            f"Date/Time: {self._format_time(message.created_at_ns)}",
            f"Bid: {bid}",
            f"Title: {message.subject}",
            "",
        )
        actions = list(self._lines(*header))
        actions.extend(self._raw_with_cr(message.body))
        actions.extend(
            self._lines(
                "",
                f"[End of Message #{message.message_id} from {message.sender}]",
                prompt=True,
            )
        )
        return ClassicBBSResult(True, "message read", tuple(actions))

    def _kill_command(self, args: list[str]) -> ClassicBBSResult:
        if len(args) != 1:
            return self._reject("usage: K <message-number>", prompt=True)
        try:
            message_id = int(args[0], 10)
            killed = self._store.kill_for(
                self._peer, message_id, killed_at_ns=self._clock()
            )
        except PersistentMailboxAuthorizationError as exc:
            return self._reject(str(exc), prompt=True)
        except (ValueError, PersistentMailboxError) as exc:
            return self._reject(f"message kill failed: {exc}", prompt=True)
        if not killed:
            return self._reject("message not found or already killed", prompt=True)
        return self._ok(f"Message {message_id} killed", prompt=True)

    def _start_personal(self, args: list[str]) -> ClassicBBSResult:
        if len(args) != 1:
            return self._reject("usage: SP <callsign>", prompt=True)
        try:
            recipient = Address.parse(args[0])
        except ValueError:
            return self._reject("invalid personal-message callsign", prompt=True)
        self._composition = _Composition(_ComposeKind.PERSONAL, str(recipient))
        return self._ok("Enter Title (only):")

    def _start_bulletin(self, args: list[str]) -> ClassicBBSResult:
        if len(args) != 1:
            return self._reject("usage: SB <topic>", prompt=True)
        topic = args[0].strip().upper()
        # Let the P1 store perform the final topic validation before deposit,
        # but reject obvious composition mistakes here without entering state.
        if not topic or len(topic) > 12 or any(
            not (char.isascii() and (char.isalnum() or char == "-")) for char in topic
        ):
            return self._reject("bulletin topic must be 1..12 letters, digits, or hyphen", prompt=True)
        self._composition = _Composition(_ComposeKind.BULLETIN, topic)
        return self._ok("Enter Title (only):")

    def _composition_line(self, raw: bytes, text: str) -> ClassicBBSResult:
        assert self._composition is not None
        marker = text.strip().upper()
        if marker == "/ABORT":
            self._clear_composition()
            return self._ok("Message aborted", prompt=True)

        if self._composition.stage is _ComposeStage.TITLE:
            try:
                encoded = text.encode("ascii")
            except UnicodeEncodeError:
                self._clear_composition()
                return self._reject("title must be ASCII", prompt=True)
            if not encoded or len(encoded) > MAX_BBS_SUBJECT_BYTES:
                self._clear_composition()
                return self._reject(
                    f"title must be 1..{MAX_BBS_SUBJECT_BYTES} printable ASCII bytes",
                    prompt=True,
                )
            self._composition.subject = text
            self._composition.stage = _ComposeStage.BODY
            return self._ok("Enter Message Text (end with /EX or /ABORT)")

        if marker == "/EX":
            assert self._composition.body is not None
            if not self._composition.body:
                return self._reject("message body is empty; use /ABORT to cancel")
            body = bytes(self._composition.body[:-1])
            composition = self._composition
            try:
                timestamp = self._clock()
                if composition.kind is _ComposeKind.PERSONAL:
                    message = self._store.deposit_personal(
                        sender=self._peer,
                        recipient=Address.parse(composition.destination),
                        subject=composition.subject,
                        body=body,
                        created_at_ns=timestamp,
                    )
                else:
                    message = self._store.deposit_bulletin(
                        sender=self._peer,
                        topic=composition.destination,
                        subject=composition.subject,
                        body=body,
                        created_at_ns=timestamp,
                    )
            except (
                PersistentMailboxError,
                PersistentMailboxQuotaError,
                PersistentMailboxDuplicateBidError,
                TypeError,
                ValueError,
            ) as exc:
                self._clear_composition()
                return self._reject(f"message not saved: {exc}", prompt=True)
            self._clear_composition()
            kind = "bulletin" if message.message_type is MailboxMessageType.BULLETIN else "message"
            return self._ok(
                f"{kind.title()} {message.message_id} saved for {message.recipient}",
                prompt=True,
            )

        addition = raw + b"\r"
        assert self._composition.body is not None
        if len(self._composition.body) + len(addition) > MAX_BBS_BODY_BYTES:
            self._clear_composition()
            return self._reject(
                f"message body exceeds {MAX_BBS_BODY_BYTES} bytes; composition aborted",
                prompt=True,
            )
        self._composition.body.extend(addition)
        return ClassicBBSResult(True, "message body line buffered")

    def _clock(self) -> int:
        value = self._now_ns()
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("mailbox clock returned invalid timestamp")
        return value

    def _prompt(self) -> str:
        return f"de {self._local}>"

    def _ok(self, *lines: str, prompt: bool = False) -> ClassicBBSResult:
        return ClassicBBSResult(True, "BBS command accepted", self._lines(*lines, prompt=prompt))

    def _reject(
        self, reason: str, *, prompt: bool = False, close: bool = False
    ) -> ClassicBBSResult:
        self._rejected += 1
        actions = self._lines(f"? {reason}", prompt=prompt, close=close)
        return ClassicBBSResult(False, reason, actions, close or self._close_requested)

    def _lines(
        self, *lines: str, prompt: bool = False, close: bool = False
    ) -> tuple[ClassicBBSAction, ...]:
        payloads: list[bytes] = []
        for line in lines:
            encoded = line.encode("ascii") + b"\r"
            payloads.extend(self._chunk(encoded))
        if prompt:
            payloads.extend(self._chunk(self._prompt().encode("ascii") + b"\r"))
        return tuple(
            ClassicBBSAction(payload, close=close and index == len(payloads) - 1)
            for index, payload in enumerate(payloads)
        )

    def _raw_with_cr(self, body: bytes) -> tuple[ClassicBBSAction, ...]:
        payload = body + (b"" if body.endswith((b"\r", b"\n")) else b"\r")
        return tuple(ClassicBBSAction(chunk) for chunk in self._chunk(payload))

    def _chunk(self, payload: bytes) -> list[bytes]:
        return [payload[start : start + self._paclen] for start in range(0, len(payload), self._paclen)]

    @staticmethod
    def _format_list_entry(entry: PersistentMailboxListEntry) -> str:
        status = "N" if entry.unread else "R"
        return (
            f"{entry.message_id:5d}  {entry.message_type.value}{status}  "
            f"{entry.body_bytes:4d}  {entry.recipient:<12.12}  "
            f"{entry.sender:<6.6}  {entry.subject}"
        )

    @staticmethod
    def _format_time(created_at_ns: int) -> str:
        moment = datetime.fromtimestamp(created_at_ns / 1_000_000_000, tz=timezone.utc)
        return moment.strftime("%d-%b %H:%MZ")

    def _clear_composition(self) -> None:
        self._composition = None


__all__ = [
    "MAX_BBS_COMMAND_BYTES",
    "MAX_BBS_INPUT_BUFFER_BYTES",
    "MIN_BBS_PACLEN",
    "MAX_BBS_PACLEN",
    "DEFAULT_BBS_LIST_LIMIT",
    "ClassicBBSAction",
    "ClassicBBSResult",
    "ClassicBBSSnapshot",
    "ClassicBBSSession",
]
