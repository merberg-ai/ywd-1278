"""0I-P3 product configuration for the persistent packet node/BBS.

This module parses and validates the future persistent node/mailbox service but
owns no runtime capability.  At P3 the daemon explicitly refuses activation;
P4 may compose the already-qualified runtime using this frozen typed config.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from ywd1278.ax25 import Address


DEFAULT_NODE_ALIAS = "YWDNOD"
DEFAULT_NODE_MAX_SESSIONS = 1
DEFAULT_MAILBOX_DATABASE = Path("/var/lib/ywd-1278/mailbox.sqlite3")
DEFAULT_MAILBOX_PACLEN = 128
DEFAULT_MAILBOX_INFO = "YWD-1278 persistent packet BBS"


class ProductNodeMailboxConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProductNodeMailboxConfig:
    node_enabled: bool
    local: Address | None
    alias: str
    max_sessions: int
    mailbox_enabled: bool
    mailbox_database: Path
    mailbox_paclen: int
    mailbox_info: str


def _optional_table(root: dict, name: str) -> dict | None:
    value = root.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProductNodeMailboxConfigurationError(f"invalid [{name}] table")
    return value


def _boolean(table: dict, key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ProductNodeMailboxConfigurationError(f"{key} must be true or false")
    return value


def _integer(table: dict, key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProductNodeMailboxConfigurationError(f"{key} must be an integer")
    return int(value)


def load_product_node_mailbox_config(path: str | Path) -> ProductNodeMailboxConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            root = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProductNodeMailboxConfigurationError(
            f"cannot load node/mailbox configuration {config_path}: {exc}"
        ) from exc

    node = _optional_table(root, "node")
    mailbox = _optional_table(root, "mailbox")
    station = _optional_table(root, "station")
    storage = _optional_table(root, "storage")

    node_enabled = False if node is None else _boolean(node, "enabled", False)
    alias = DEFAULT_NODE_ALIAS
    max_sessions = DEFAULT_NODE_MAX_SESSIONS
    if node is not None:
        raw_alias = node.get("alias", DEFAULT_NODE_ALIAS)
        if not isinstance(raw_alias, str):
            raise ProductNodeMailboxConfigurationError("node.alias must be a string")
        alias = raw_alias.strip().upper()
        if not 1 <= len(alias) <= 6 or not alias.isascii() or not alias.isalnum():
            raise ProductNodeMailboxConfigurationError(
                "node.alias must be 1..6 alphanumeric ASCII characters"
            )
        max_sessions = _integer(node, "max_sessions", DEFAULT_NODE_MAX_SESSIONS)
        if max_sessions != 1:
            raise ProductNodeMailboxConfigurationError(
                "node.max_sessions must remain 1 until sustained multi-session qualification"
            )

    mailbox_enabled = False if mailbox is None else _boolean(mailbox, "enabled", False)
    database = DEFAULT_MAILBOX_DATABASE
    paclen = DEFAULT_MAILBOX_PACLEN
    info = DEFAULT_MAILBOX_INFO
    if mailbox is not None:
        raw_database = mailbox.get("database", str(DEFAULT_MAILBOX_DATABASE))
        if not isinstance(raw_database, str):
            raise ProductNodeMailboxConfigurationError("mailbox.database must be a string")
        database = Path(raw_database.strip())
        if not database.is_absolute():
            raise ProductNodeMailboxConfigurationError("mailbox.database must be an absolute path")
        paclen = _integer(mailbox, "paclen", DEFAULT_MAILBOX_PACLEN)
        if not 32 <= paclen <= 256:
            raise ProductNodeMailboxConfigurationError("mailbox.paclen must be 32..256")
        raw_info = mailbox.get("info", DEFAULT_MAILBOX_INFO)
        if not isinstance(raw_info, str) or not raw_info:
            raise ProductNodeMailboxConfigurationError("mailbox.info must be a non-empty string")
        try:
            encoded_info = raw_info.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ProductNodeMailboxConfigurationError("mailbox.info must be ASCII") from exc
        if len(encoded_info) > 160 or any(byte not in (9,) and not 32 <= byte <= 126 for byte in encoded_info):
            raise ProductNodeMailboxConfigurationError(
                "mailbox.info must be at most 160 printable ASCII bytes"
            )
        info = raw_info

    local: Address | None = None
    if node_enabled or mailbox_enabled:
        if station is None:
            raise ProductNodeMailboxConfigurationError(
                "enabled node/mailbox service requires [station] identity"
            )
        callsign = station.get("callsign")
        ssid = station.get("ssid")
        if not isinstance(callsign, str):
            raise ProductNodeMailboxConfigurationError("station.callsign must be a string")
        if isinstance(ssid, bool) or not isinstance(ssid, int):
            raise ProductNodeMailboxConfigurationError("station.ssid must be an integer")
        try:
            local = Address(callsign, ssid)
        except (TypeError, ValueError) as exc:
            raise ProductNodeMailboxConfigurationError(
                f"invalid station identity for node/mailbox: {exc}"
            ) from exc

    if mailbox_enabled and not node_enabled:
        raise ProductNodeMailboxConfigurationError(
            "mailbox.enabled=true requires node.enabled=true"
        )
    if node_enabled and not mailbox_enabled:
        # P3/P4 define one persistent classic node+BBS product boundary rather
        # than creating a second independently-qualified node-only runtime.
        raise ProductNodeMailboxConfigurationError(
            "node.enabled=true requires mailbox.enabled=true for the 0I service"
        )

    if storage is not None:
        monitor_database = storage.get("database")
        if isinstance(monitor_database, str) and Path(monitor_database.strip()) == database:
            raise ProductNodeMailboxConfigurationError(
                "mailbox.database must be separate from storage.database"
            )

    return ProductNodeMailboxConfig(
        node_enabled=node_enabled,
        local=local,
        alias=alias,
        max_sessions=max_sessions,
        mailbox_enabled=mailbox_enabled,
        mailbox_database=database,
        mailbox_paclen=paclen,
        mailbox_info=info,
    )


__all__ = [
    "DEFAULT_NODE_ALIAS",
    "DEFAULT_NODE_MAX_SESSIONS",
    "DEFAULT_MAILBOX_DATABASE",
    "DEFAULT_MAILBOX_PACLEN",
    "DEFAULT_MAILBOX_INFO",
    "ProductNodeMailboxConfigurationError",
    "ProductNodeMailboxConfig",
    "load_product_node_mailbox_config",
]
