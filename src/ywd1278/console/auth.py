"""Credential hashing and protected auth-file helpers for the 0E-P3 console.

The credential file stores a username plus a salted PBKDF2-HMAC-SHA256 password
verifier. Plaintext passwords are never written to disk by this module.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import getpass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import stat


HASH_SCHEME = "pbkdf2-sha256"
PBKDF2_ITERATIONS = 310_000
MIN_PBKDF2_ITERATIONS = 200_000
MAX_PBKDF2_ITERATIONS = 1_000_000
SALT_BYTES = 16
DIGEST_BYTES = 32
MAX_AUTH_FILE_BYTES = 1024
MAX_USERNAME_CHARS = 32
MIN_PASSWORD_CHARS = 10
MAX_PASSWORD_CHARS = 128
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


@dataclass(frozen=True)
class CredentialRecord:
    username: str
    password_hash: str


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(text: str) -> bytes:
    if not text or not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise ValueError("invalid base64 field")
    padding = "=" * (-len(text) % 4)
    try:
        return base64.b64decode(text + padding, altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("invalid base64 field") from exc


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not _USERNAME_RE.fullmatch(username):
        raise ValueError(
            "username must be 1..32 ASCII letters, digits, dot, underscore, or hyphen"
        )
    return username


def validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    if not MIN_PASSWORD_CHARS <= len(password) <= MAX_PASSWORD_CHARS:
        raise ValueError(
            f"password must be {MIN_PASSWORD_CHARS}..{MAX_PASSWORD_CHARS} characters"
        )
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in password):
        raise ValueError("password must contain printable ASCII characters only")
    return password


def hash_password(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = PBKDF2_ITERATIONS,
) -> str:
    password = validate_password(password)
    if type(iterations) is not int or not MIN_PBKDF2_ITERATIONS <= iterations <= MAX_PBKDF2_ITERATIONS:
        raise ValueError(
            f"iterations must be {MIN_PBKDF2_ITERATIONS}..{MAX_PBKDF2_ITERATIONS}"
        )
    if salt is None:
        salt = secrets.token_bytes(SALT_BYTES)
    if not isinstance(salt, bytes) or len(salt) != SALT_BYTES:
        raise ValueError(f"salt must be exactly {SALT_BYTES} bytes")

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("ascii"),
        salt,
        iterations,
        dklen=DIGEST_BYTES,
    )
    return "$".join(
        (
            HASH_SCHEME,
            str(iterations),
            _urlsafe_b64encode(salt),
            _urlsafe_b64encode(digest),
        )
    )


def _parse_password_hash(encoded: str) -> tuple[int, bytes, bytes]:
    if not isinstance(encoded, str):
        raise TypeError("password hash must be a string")
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != HASH_SCHEME:
        raise ValueError("unsupported password hash format")
    try:
        iterations = int(parts[1], 10)
    except ValueError as exc:
        raise ValueError("invalid password hash iteration count") from exc
    if not MIN_PBKDF2_ITERATIONS <= iterations <= MAX_PBKDF2_ITERATIONS:
        raise ValueError("password hash iteration count is outside qualified bounds")
    salt = _urlsafe_b64decode(parts[2])
    digest = _urlsafe_b64decode(parts[3])
    if len(salt) != SALT_BYTES or len(digest) != DIGEST_BYTES:
        raise ValueError("password hash salt/digest size is invalid")
    return iterations, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    try:
        password = validate_password(password)
        iterations, salt, expected = _parse_password_hash(encoded)
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("ascii"),
        salt,
        iterations,
        dklen=DIGEST_BYTES,
    )
    return hmac.compare_digest(actual, expected)


def encode_credential(record: CredentialRecord) -> str:
    username = validate_username(record.username)
    _parse_password_hash(record.password_hash)
    return f"{username}:{record.password_hash}\n"


def parse_credential(text: str) -> CredentialRecord:
    if not isinstance(text, str):
        raise TypeError("credential text must be a string")
    if "\x00" in text or "\r" in text:
        raise ValueError("credential file contains invalid control data")
    lines = text.splitlines()
    if len(lines) != 1 or ":" not in lines[0]:
        raise ValueError("credential file must contain exactly one username:hash record")
    username, password_hash = lines[0].split(":", 1)
    username = validate_username(username)
    _parse_password_hash(password_hash)
    return CredentialRecord(username=username, password_hash=password_hash)


def load_credential_file(path: str | os.PathLike[str]) -> CredentialRecord:
    path_string = os.fspath(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path_string, flags)
    except OSError as exc:
        raise ValueError(f"cannot open auth file: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("auth file must be a regular file")
        if info.st_mode & 0o077:
            raise ValueError("auth file permissions must not grant group/world access")
        if info.st_size <= 0 or info.st_size > MAX_AUTH_FILE_BYTES:
            raise ValueError(f"auth file must be 1..{MAX_AUTH_FILE_BYTES} bytes")
        payload = os.read(fd, MAX_AUTH_FILE_BYTES + 1)
        if len(payload) > MAX_AUTH_FILE_BYTES:
            raise ValueError(f"auth file exceeds {MAX_AUTH_FILE_BYTES} bytes")
    finally:
        os.close(fd)
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("auth file must contain ASCII text") from exc
    return parse_credential(text)


def write_credential_file(
    path: str | os.PathLike[str],
    record: CredentialRecord,
    *,
    overwrite: bool = False,
) -> None:
    destination = Path(path)
    payload = encode_credential(record).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    fd = os.open(destination, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        written = os.write(fd, payload)
        if written != len(payload):
            raise OSError("short write while creating auth file")
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ywd1278.console.auth",
        description="Create a protected hash-only YWD-1278 console credential file",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", required=True, metavar="PATH")
    parser.add_argument("--force", action="store_true", help="replace an existing file")
    args = parser.parse_args(argv)

    try:
        username = validate_username(args.username)
        first = getpass.getpass("New console password: ")
        second = getpass.getpass("Confirm console password: ")
        if first != second:
            parser.error("passwords do not match")
        password_hash = hash_password(first)
        record = CredentialRecord(username=username, password_hash=password_hash)
        write_credential_file(args.output, record, overwrite=args.force)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Created protected console credential file: {args.output}")
    print("Stored password material: salted PBKDF2-HMAC-SHA256 verifier only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
