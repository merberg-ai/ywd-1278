"""0I-P1 persistent classic packet mailbox core; no runtime or RF ownership.

This module intentionally lives beside the frozen 0H mailbox prototype.  It is
for the real persistent BBS service and therefore has its own schema and file.
It provides personal mail, bulletins, per-user new/read state, owner-safe soft
kill, optional BIDs, bounded quotas, and callsign mailbox identity shared across
SSIDs.  It does not open a packet link, schedule forwarding, transmit RF, or
own the product daemon lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import sqlite3
import stat

from ywd1278.ax25 import Address


BBS_MAILBOX_SCHEMA_VERSION = 1
MAX_BBS_SUBJECT_BYTES = 64
MAX_BBS_BODY_BYTES = 4096
MAX_BBS_BID_BYTES = 64
MAX_BBS_TOPIC_BYTES = 12
MAX_BBS_MESSAGES_PER_USER = 200
MAX_BBS_BULLETINS = 500
MAX_BBS_MESSAGES_TOTAL = 2000
MAX_BBS_LIST_ENTRIES = 100

_TOPIC_RE = re.compile(r"^[A-Z0-9-]{1,12}$")


class PersistentMailboxError(RuntimeError):
    pass


class PersistentMailboxSchemaError(PersistentMailboxError):
    pass


class PersistentMailboxQuotaError(PersistentMailboxError):
    pass


class PersistentMailboxAuthorizationError(PersistentMailboxError):
    pass


class PersistentMailboxDuplicateBidError(PersistentMailboxError):
    pass


class MailboxMessageType(Enum):
    PERSONAL = "P"
    BULLETIN = "B"


@dataclass(frozen=True)
class PersistentMailboxMessage:
    message_id: int
    message_type: MailboxMessageType
    sender: str
    recipient: str
    subject: str
    body: bytes
    created_at_ns: int
    bid: str | None
    killed_at_ns: int | None


@dataclass(frozen=True)
class PersistentMailboxListEntry:
    message_id: int
    message_type: MailboxMessageType
    sender: str
    recipient: str
    subject: str
    body_bytes: int
    created_at_ns: int
    bid: str | None
    unread: bool


@dataclass(frozen=True)
class PersistentMailboxCounts:
    visible: int
    new: int
    personal_new: int
    bulletin_new: int
    sent: int


class PersistentMailboxStore:
    """Protected SQLite store for the persistent classic BBS mailbox.

    Mailbox identity is the base AX.25 callsign rather than a specific SSID, so
    (for example) KJ6YWD-1 and KJ6YWD-15 share the KJ6YWD mailbox.  Link/session
    authorization remains the responsibility of the caller.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.is_absolute():
            raise ValueError("persistent mailbox path must be absolute")
        if self._path.exists() and self._path.is_symlink():
            raise PersistentMailboxError("persistent mailbox path must not be a symlink")
        if not self._path.parent.is_dir():
            raise PersistentMailboxError("persistent mailbox parent directory must already exist")
        if not self._path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self._path, flags, 0o600)
            os.close(descriptor)
        initial = os.lstat(self._path)
        if not stat.S_ISREG(initial.st_mode):
            raise PersistentMailboxError("persistent mailbox path must be a regular file")
        self._file_identity = (initial.st_dev, initial.st_ino)
        with self._connect() as connection:
            self._prepare_schema(connection)
        os.chmod(self._path, 0o600)

    @property
    def path(self) -> Path:
        return self._path

    def deposit_personal(
        self,
        *,
        sender: Address,
        recipient: Address,
        subject: str,
        body: bytes,
        created_at_ns: int,
        bid: str | None = None,
    ) -> PersistentMailboxMessage:
        return self._deposit(
            message_type=MailboxMessageType.PERSONAL,
            sender=self._mailbox_identity(sender, "sender"),
            recipient=self._mailbox_identity(recipient, "recipient"),
            subject=self._subject(subject),
            body=self._body(body),
            created_at_ns=self._timestamp(created_at_ns, "created_at_ns"),
            bid=self._bid(bid),
        )

    def deposit_bulletin(
        self,
        *,
        sender: Address,
        topic: str,
        subject: str,
        body: bytes,
        created_at_ns: int,
        bid: str | None = None,
    ) -> PersistentMailboxMessage:
        return self._deposit(
            message_type=MailboxMessageType.BULLETIN,
            sender=self._mailbox_identity(sender, "sender"),
            recipient=self._topic(topic),
            subject=self._subject(subject),
            body=self._body(body),
            created_at_ns=self._timestamp(created_at_ns, "created_at_ns"),
            bid=self._bid(bid),
        )

    def list_visible(
        self,
        user: Address,
        *,
        limit: int = 20,
        new_only: bool = False,
        oldest_first: bool = False,
        include_bulletins: bool = True,
    ) -> tuple[PersistentMailboxListEntry, ...]:
        identity = self._mailbox_identity(user, "user")
        bounded = self._list_limit(limit)
        if not isinstance(new_only, bool) or not isinstance(oldest_first, bool):
            raise TypeError("new_only and oldest_first must be bool")
        if not isinstance(include_bulletins, bool):
            raise TypeError("include_bulletins must be bool")
        bulletin_clause = " OR m.message_type = 'B'" if include_bulletins else ""
        unread_clause = " AND r.message_id IS NULL" if new_only else ""
        order = "ASC" if oldest_first else "DESC"
        sql = (
            "SELECT m.id,m.message_type,m.sender,m.recipient,m.subject,length(m.body),"
            "m.created_at_ns,m.bid,r.message_id "
            "FROM messages m LEFT JOIN message_reads r "
            "ON r.message_id=m.id AND r.user=? "
            "WHERE m.killed_at_ns IS NULL AND ((m.message_type='P' AND m.recipient=?)"
            f"{bulletin_clause}){unread_clause} ORDER BY m.id {order} LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, (identity, identity, bounded)).fetchall()
        return tuple(self._entry(row) for row in rows)

    def list_sent(
        self,
        user: Address,
        *,
        limit: int = 20,
        oldest_first: bool = False,
    ) -> tuple[PersistentMailboxListEntry, ...]:
        identity = self._mailbox_identity(user, "user")
        bounded = self._list_limit(limit)
        if not isinstance(oldest_first, bool):
            raise TypeError("oldest_first must be bool")
        order = "ASC" if oldest_first else "DESC"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT m.id,m.message_type,m.sender,m.recipient,m.subject,length(m.body),"
                "m.created_at_ns,m.bid,r.message_id FROM messages m "
                "LEFT JOIN message_reads r ON r.message_id=m.id AND r.user=? "
                "WHERE m.killed_at_ns IS NULL AND m.sender=? "
                f"ORDER BY m.id {order} LIMIT ?",
                (identity, identity, bounded),
            ).fetchall()
        return tuple(self._entry(row) for row in rows)

    def read_for(
        self,
        user: Address,
        message_id: int,
        *,
        read_at_ns: int,
    ) -> PersistentMailboxMessage | None:
        identity = self._mailbox_identity(user, "user")
        identifier = self._message_id(message_id)
        timestamp = self._timestamp(read_at_ns, "read_at_ns")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id,message_type,sender,recipient,subject,body,created_at_ns,bid,killed_at_ns "
                "FROM messages WHERE id=? AND killed_at_ns IS NULL AND "
                "((message_type='P' AND recipient=?) OR message_type='B')",
                (identifier, identity),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            connection.execute(
                "INSERT INTO message_reads(message_id,user,read_at_ns) VALUES(?,?,?) "
                "ON CONFLICT(message_id,user) DO NOTHING",
                (identifier, identity, timestamp),
            )
            connection.commit()
        return self._message(row)

    def kill_for(self, user: Address, message_id: int, *, killed_at_ns: int) -> bool:
        identity = self._mailbox_identity(user, "user")
        identifier = self._message_id(message_id)
        timestamp = self._timestamp(killed_at_ns, "killed_at_ns")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT message_type,sender,recipient,killed_at_ns FROM messages WHERE id=?",
                (identifier,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            message_type = MailboxMessageType(str(row[0]))
            sender, recipient, already_killed = str(row[1]), str(row[2]), row[3]
            if already_killed is not None:
                connection.rollback()
                return False
            authorized = sender == identity or (
                message_type is MailboxMessageType.PERSONAL and recipient == identity
            )
            if not authorized:
                connection.rollback()
                raise PersistentMailboxAuthorizationError(
                    "only the personal recipient or original sender may kill this message"
                )
            cursor = connection.execute(
                "UPDATE messages SET killed_at_ns=? WHERE id=? AND killed_at_ns IS NULL",
                (timestamp, identifier),
            )
            connection.commit()
        return cursor.rowcount == 1

    def counts_for(self, user: Address) -> PersistentMailboxCounts:
        identity = self._mailbox_identity(user, "user")
        with self._connect() as connection:
            visible, new, personal_new, bulletin_new = connection.execute(
                "SELECT "
                "COUNT(*),"
                "SUM(CASE WHEN r.message_id IS NULL THEN 1 ELSE 0 END),"
                "SUM(CASE WHEN m.message_type='P' AND r.message_id IS NULL THEN 1 ELSE 0 END),"
                "SUM(CASE WHEN m.message_type='B' AND r.message_id IS NULL THEN 1 ELSE 0 END) "
                "FROM messages m LEFT JOIN message_reads r "
                "ON r.message_id=m.id AND r.user=? "
                "WHERE m.killed_at_ns IS NULL AND "
                "((m.message_type='P' AND m.recipient=?) OR m.message_type='B')",
                (identity, identity),
            ).fetchone()
            sent = int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE killed_at_ns IS NULL AND sender=?",
                    (identity,),
                ).fetchone()[0]
            )
        return PersistentMailboxCounts(
            int(visible or 0),
            int(new or 0),
            int(personal_new or 0),
            int(bulletin_new or 0),
            sent,
        )

    def _deposit(
        self,
        *,
        message_type: MailboxMessageType,
        sender: str,
        recipient: str,
        subject: str,
        body: bytes,
        created_at_ns: int,
        bid: str | None,
    ) -> PersistentMailboxMessage:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            total = int(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
            if total >= MAX_BBS_MESSAGES_TOTAL:
                raise PersistentMailboxQuotaError("persistent mailbox global quota reached")
            if message_type is MailboxMessageType.PERSONAL:
                active = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE message_type='P' AND recipient=? "
                        "AND killed_at_ns IS NULL",
                        (recipient,),
                    ).fetchone()[0]
                )
                if active >= MAX_BBS_MESSAGES_PER_USER:
                    raise PersistentMailboxQuotaError("recipient persistent mailbox quota reached")
            else:
                active = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE message_type='B' AND killed_at_ns IS NULL"
                    ).fetchone()[0]
                )
                if active >= MAX_BBS_BULLETINS:
                    raise PersistentMailboxQuotaError("persistent bulletin quota reached")
            try:
                cursor = connection.execute(
                    "INSERT INTO messages(message_type,sender,recipient,subject,body,created_at_ns,bid) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        message_type.value,
                        sender,
                        recipient,
                        subject,
                        sqlite3.Binary(body),
                        created_at_ns,
                        bid,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                if bid is not None and "bid" in str(exc).lower():
                    raise PersistentMailboxDuplicateBidError(f"duplicate BID {bid}") from exc
                raise PersistentMailboxError(f"persistent mailbox insert failed: {exc}") from exc
            message_id = int(cursor.lastrowid)
            connection.commit()
        return PersistentMailboxMessage(
            message_id,
            message_type,
            sender,
            recipient,
            subject,
            body,
            created_at_ns,
            bid,
            None,
        )

    def _connect(self) -> sqlite3.Connection:
        before = os.lstat(self._path)
        if stat.S_ISLNK(before.st_mode) or (before.st_dev, before.st_ino) != self._file_identity:
            raise PersistentMailboxError("persistent mailbox file identity changed")
        connection = sqlite3.connect(self._path, timeout=5.0)
        after = os.lstat(self._path)
        if (after.st_dev, after.st_ino) != self._file_identity:
            connection.close()
            raise PersistentMailboxError("persistent mailbox file identity changed while opening")
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
                raise PersistentMailboxSchemaError(
                    "refusing unversioned non-empty persistent mailbox"
                )
            connection.executescript(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_type TEXT NOT NULL CHECK(message_type IN ('P','B')),
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body BLOB NOT NULL,
                    created_at_ns INTEGER NOT NULL CHECK(created_at_ns >= 0),
                    bid TEXT UNIQUE,
                    killed_at_ns INTEGER CHECK(killed_at_ns IS NULL OR killed_at_ns >= 0)
                );
                CREATE INDEX messages_recipient_id_idx ON messages(recipient,id DESC);
                CREATE INDEX messages_sender_id_idx ON messages(sender,id DESC);
                CREATE INDEX messages_type_id_idx ON messages(message_type,id DESC);
                CREATE TABLE message_reads (
                    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    user TEXT NOT NULL,
                    read_at_ns INTEGER NOT NULL CHECK(read_at_ns >= 0),
                    PRIMARY KEY(message_id,user)
                );
                CREATE INDEX message_reads_user_id_idx ON message_reads(user,message_id DESC);
                PRAGMA user_version=1;
                """
            )
            connection.commit()
        elif version != BBS_MAILBOX_SCHEMA_VERSION:
            raise PersistentMailboxSchemaError(
                f"unsupported persistent mailbox schema version {version}"
            )
        message_columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(messages)")
        )
        if message_columns != (
            "id",
            "message_type",
            "sender",
            "recipient",
            "subject",
            "body",
            "created_at_ns",
            "bid",
            "killed_at_ns",
        ):
            raise PersistentMailboxSchemaError("persistent messages table does not match schema v1")
        read_columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(message_reads)")
        )
        if read_columns != ("message_id", "user", "read_at_ns"):
            raise PersistentMailboxSchemaError("persistent message_reads table does not match schema v1")

    @staticmethod
    def _mailbox_identity(value: Address, name: str) -> str:
        if not isinstance(value, Address):
            raise TypeError(f"{name} must be an AX.25 Address")
        return Address(value.callsign, 0).callsign

    @staticmethod
    def _topic(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("bulletin topic must be str")
        topic = value.strip().upper()
        if not _TOPIC_RE.fullmatch(topic):
            raise ValueError("bulletin topic must be 1..12 ASCII letters, digits, or hyphen")
        return topic

    @staticmethod
    def _subject(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("subject must be str")
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("subject must be ASCII") from exc
        if not encoded or len(encoded) > MAX_BBS_SUBJECT_BYTES:
            raise ValueError(f"subject must be 1..{MAX_BBS_SUBJECT_BYTES} ASCII bytes")
        if any(byte < 32 or byte > 126 for byte in encoded):
            raise ValueError("subject must contain printable ASCII only")
        return value

    @staticmethod
    def _body(value: bytes) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError("body must be bytes")
        if not value or len(value) > MAX_BBS_BODY_BYTES:
            raise ValueError(f"body must be 1..{MAX_BBS_BODY_BYTES} bytes")
        if any(byte not in (10, 13) and not 32 <= byte <= 126 for byte in value):
            raise ValueError("body must contain printable ASCII plus CR/LF only")
        return bytes(value)

    @staticmethod
    def _bid(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("BID must be str or None")
        clean = value.strip().upper()
        try:
            encoded = clean.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("BID must be ASCII") from exc
        if not encoded or len(encoded) > MAX_BBS_BID_BYTES:
            raise ValueError(f"BID must be 1..{MAX_BBS_BID_BYTES} ASCII bytes")
        if any(byte < 33 or byte > 126 for byte in encoded):
            raise ValueError("BID must contain visible ASCII without spaces")
        return clean

    @staticmethod
    def _timestamp(value: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
        return value

    @staticmethod
    def _message_id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("message_id must be a positive integer")
        return value

    @staticmethod
    def _list_limit(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BBS_LIST_ENTRIES:
            raise ValueError(f"limit must be an integer 1..{MAX_BBS_LIST_ENTRIES}")
        return value

    @staticmethod
    def _message(row: tuple[object, ...]) -> PersistentMailboxMessage:
        return PersistentMailboxMessage(
            int(row[0]),
            MailboxMessageType(str(row[1])),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            bytes(row[5]),
            int(row[6]),
            None if row[7] is None else str(row[7]),
            None if row[8] is None else int(row[8]),
        )

    @staticmethod
    def _entry(row: tuple[object, ...]) -> PersistentMailboxListEntry:
        return PersistentMailboxListEntry(
            int(row[0]),
            MailboxMessageType(str(row[1])),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            int(row[5]),
            int(row[6]),
            None if row[7] is None else str(row[7]),
            row[8] is None,
        )


__all__ = [
    "BBS_MAILBOX_SCHEMA_VERSION",
    "MAX_BBS_SUBJECT_BYTES",
    "MAX_BBS_BODY_BYTES",
    "MAX_BBS_BID_BYTES",
    "MAX_BBS_TOPIC_BYTES",
    "MAX_BBS_MESSAGES_PER_USER",
    "MAX_BBS_BULLETINS",
    "MAX_BBS_MESSAGES_TOTAL",
    "MAX_BBS_LIST_ENTRIES",
    "PersistentMailboxError",
    "PersistentMailboxSchemaError",
    "PersistentMailboxQuotaError",
    "PersistentMailboxAuthorizationError",
    "PersistentMailboxDuplicateBidError",
    "MailboxMessageType",
    "PersistentMailboxMessage",
    "PersistentMailboxListEntry",
    "PersistentMailboxCounts",
    "PersistentMailboxStore",
]
