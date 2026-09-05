"""0H-P2 bounded SQLite mailbox storage with no runtime or RF ownership."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import stat

from ywd1278.ax25 import Address


MAILBOX_SCHEMA_VERSION = 1
MAX_SUBJECT_BYTES = 64
MAX_BODY_BYTES = 4096
MAX_MESSAGES_PER_RECIPIENT = 100
MAX_MESSAGES_TOTAL = 1000


class MailboxError(RuntimeError):
    pass


class MailboxSchemaError(MailboxError):
    pass


class MailboxQuotaError(MailboxError):
    pass


@dataclass(frozen=True)
class MailboxMessage:
    message_id: int
    sender: str
    recipient: str
    subject: str
    body: bytes
    created_at_ns: int


@dataclass(frozen=True)
class MailboxMessageSummary:
    message_id: int
    sender: str
    subject: str
    body_bytes: int
    created_at_ns: int


class MailboxStore:
    """Open short SQLite transactions against one protected mailbox file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.is_absolute():
            raise ValueError("mailbox path must be absolute")
        if self._path.exists() and self._path.is_symlink():
            raise MailboxError("mailbox path must not be a symlink")
        if not self._path.parent.is_dir():
            raise MailboxError("mailbox parent directory must already exist")
        if not self._path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self._path, flags, 0o600)
            os.close(descriptor)
        initial = os.lstat(self._path)
        if not stat.S_ISREG(initial.st_mode):
            raise MailboxError("mailbox path must be a regular file")
        self._file_identity = (initial.st_dev, initial.st_ino)
        with self._connect() as connection:
            self._prepare_schema(connection)
        os.chmod(self._path, 0o600)

    @property
    def path(self) -> Path:
        return self._path

    def deposit(
        self,
        *,
        sender: Address,
        recipient: Address,
        subject: str,
        body: bytes,
        created_at_ns: int,
    ) -> MailboxMessage:
        source = self._identity(sender, "sender")
        destination = self._identity(recipient, "recipient")
        clean_subject = self._subject(subject)
        clean_body = self._body(body)
        timestamp = self._timestamp(created_at_ns)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            total = int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
            if total >= MAX_MESSAGES_TOTAL:
                raise MailboxQuotaError("global mailbox quota reached")
            per_recipient = int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE recipient = ?", (destination,)
                ).fetchone()[0]
            )
            if per_recipient >= MAX_MESSAGES_PER_RECIPIENT:
                raise MailboxQuotaError("recipient mailbox quota reached")
            cursor = connection.execute(
                "INSERT INTO messages(sender, recipient, subject, body, created_at_ns) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, destination, clean_subject, sqlite3.Binary(clean_body), timestamp),
            )
            message_id = int(cursor.lastrowid)
            connection.commit()
        return MailboxMessage(
            message_id, source, destination, clean_subject, clean_body, timestamp
        )

    def list_for(self, recipient: Address, *, limit: int = 20) -> tuple[MailboxMessageSummary, ...]:
        destination = self._identity(recipient, "recipient")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer 1..100")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, sender, subject, length(body), created_at_ns FROM messages "
                "WHERE recipient = ? ORDER BY id DESC LIMIT ?",
                (destination, limit),
            ).fetchall()
        return tuple(MailboxMessageSummary(int(a), str(b), str(c), int(d), int(e)) for a, b, c, d, e in rows)

    def read_for(self, recipient: Address, message_id: int) -> MailboxMessage | None:
        destination = self._identity(recipient, "recipient")
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id < 1:
            raise ValueError("message_id must be a positive integer")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, sender, recipient, subject, body, created_at_ns "
                "FROM messages WHERE id = ? AND recipient = ?",
                (message_id, destination),
            ).fetchone()
        if row is None:
            return None
        return MailboxMessage(int(row[0]), str(row[1]), str(row[2]), str(row[3]), bytes(row[4]), int(row[5]))

    def _connect(self) -> sqlite3.Connection:
        before = os.lstat(self._path)
        if stat.S_ISLNK(before.st_mode) or (before.st_dev, before.st_ino) != self._file_identity:
            raise MailboxError("mailbox file identity changed")
        connection = sqlite3.connect(self._path, timeout=5.0)
        after = os.lstat(self._path)
        if (after.st_dev, after.st_ino) != self._file_identity:
            connection.close()
            raise MailboxError("mailbox file identity changed while opening")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _prepare_schema(connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if tables:
                raise MailboxSchemaError("refusing unversioned non-empty mailbox")
            connection.executescript(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body BLOB NOT NULL,
                    created_at_ns INTEGER NOT NULL CHECK(created_at_ns >= 0)
                );
                CREATE INDEX messages_recipient_id_idx ON messages(recipient, id DESC);
                PRAGMA user_version=1;
                """
            )
            connection.commit()
        elif version != MAILBOX_SCHEMA_VERSION:
            raise MailboxSchemaError(f"unsupported mailbox schema version {version}")
        columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(messages)"))
        if columns != ("id", "sender", "recipient", "subject", "body", "created_at_ns"):
            raise MailboxSchemaError("messages table does not match schema v1")

    @staticmethod
    def _identity(value: Address, name: str) -> str:
        if not isinstance(value, Address):
            raise TypeError(f"{name} must be an AX.25 Address")
        return str(Address(value.callsign, value.ssid))

    @staticmethod
    def _subject(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("subject must be str")
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("subject must be ASCII") from exc
        if not encoded or len(encoded) > MAX_SUBJECT_BYTES or any(byte < 32 or byte > 126 for byte in encoded):
            raise ValueError("subject must be 1..64 printable ASCII bytes")
        return value

    @staticmethod
    def _body(value: bytes) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError("body must be bytes")
        if not value or len(value) > MAX_BODY_BYTES:
            raise ValueError("body must be 1..4096 bytes")
        if any(byte not in (10, 13) and not 32 <= byte <= 126 for byte in value):
            raise ValueError("body must contain printable ASCII plus CR/LF only")
        return bytes(value)

    @staticmethod
    def _timestamp(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("created_at_ns must be a non-negative integer")
        return value


__all__ = ["MailboxError", "MailboxSchemaError", "MailboxQuotaError", "MailboxMessage", "MailboxMessageSummary", "MailboxStore"]
