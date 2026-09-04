"""Configuration/file-only trust checks for the Stage-F product firmware gate.

This module deliberately performs no modem, GPIO, systemd, programmer, or RF
operations.  Hardware-changing shell code may call these checks, but trust is
recorded only after exact artifact, stock-backup, programmed-readback, runtime
identity, and no-TX configuration evidence agree with the product profile.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from ywd1278.install.readiness import READY, inspect_runtime_readiness


class FirmwareTrustError(ValueError):
    pass


@dataclass(frozen=True)
class ProductFirmwareProfile:
    path: Path
    target_id: str
    expected_identity: str
    artifact_relative_path: str
    artifact_size_bytes: int
    artifact_sha256: str
    flash_base: str
    programmed_readback_bytes: int
    programmed_readback_sha256: str
    stock_flash_size_bytes: int
    stock_flash_sha256: str
    expected_bootloader_version: str
    expected_device_id: str
    flash_authorization_token: str
    service_eligibility_record: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirmwareTrustError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FirmwareTrustError(f"JSON root must be an object: {path}")
    return value


def load_product_firmware_profile(path: str | Path) -> ProductFirmwareProfile:
    p = Path(path)
    data = _load_json(p)
    if data.get("schema") != 1 or data.get("product") != "YWD-1278" or data.get("series") != "AX25R4":
        raise FirmwareTrustError("unexpected product firmware profile")
    safety = data.get("safety")
    if not isinstance(safety, dict):
        raise FirmwareTrustError("missing firmware safety object")
    exact_required = {
        "product_flash_enabled": True,
        "automatic_flash_enabled": False,
        "requires_runtime_readiness_ready": True,
        "requires_exact_target": True,
        "requires_exact_artifact_hash": True,
        "requires_verified_stock_backup": True,
        "requires_programmed_readback": True,
        "requires_exact_runtime_identity": True,
        "option_bytes_permitted": False,
        "tx_must_remain_disabled": True,
        "service_enable_permitted_by_this_stage": False,
    }
    for key, expected in exact_required.items():
        if safety.get(key) is not expected:
            raise FirmwareTrustError(f"unsafe product firmware profile: safety.{key}")

    def required_str(key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise FirmwareTrustError(f"profile field {key} must be a non-empty string")
        return value

    def required_int(key: str) -> int:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise FirmwareTrustError(f"profile field {key} must be a positive integer")
        return value

    artifact_sha = required_str("artifact_sha256").lower()
    readback_sha = required_str("programmed_readback_sha256").lower()
    stock_sha = required_str("stock_flash_sha256").lower()
    for label, digest in (("artifact", artifact_sha), ("readback", readback_sha), ("stock", stock_sha)):
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise FirmwareTrustError(f"invalid {label} SHA256")
    if artifact_sha != readback_sha:
        raise FirmwareTrustError("artifact and programmed-readback SHA256 must match")

    artifact_size = required_int("artifact_size_bytes")
    readback_bytes = required_int("programmed_readback_bytes")
    if artifact_size != readback_bytes:
        raise FirmwareTrustError("artifact size and programmed-readback length must match")

    return ProductFirmwareProfile(
        path=p,
        target_id=required_str("target_id"),
        expected_identity=required_str("expected_identity"),
        artifact_relative_path=required_str("artifact_relative_path"),
        artifact_size_bytes=artifact_size,
        artifact_sha256=artifact_sha,
        flash_base=required_str("flash_base"),
        programmed_readback_bytes=readback_bytes,
        programmed_readback_sha256=readback_sha,
        stock_flash_size_bytes=required_int("stock_flash_size_bytes"),
        stock_flash_sha256=stock_sha,
        expected_bootloader_version=required_str("expected_bootloader_version").lower(),
        expected_device_id=required_str("expected_device_id").lower(),
        flash_authorization_token=required_str("flash_authorization_token"),
        service_eligibility_record=required_str("service_eligibility_record"),
    )


def verify_artifact(profile: ProductFirmwareProfile, firmware: str | Path) -> str:
    path = Path(firmware)
    if not path.is_file():
        raise FirmwareTrustError(f"firmware artifact not found: {path}")
    size = path.stat().st_size
    if size != profile.artifact_size_bytes:
        raise FirmwareTrustError(
            f"firmware artifact size mismatch: expected {profile.artifact_size_bytes}, got {size}"
        )
    digest = _sha256(path)
    if digest != profile.artifact_sha256:
        raise FirmwareTrustError(
            f"firmware artifact SHA256 mismatch: expected {profile.artifact_sha256}, got {digest}"
        )
    return digest


def verify_stock_backup(
    profile: ProductFirmwareProfile,
    backup_dir: str | Path,
    *,
    expected_target_id: str | None = None,
) -> str:
    directory = Path(backup_dir)
    manifest_path = directory / "manifest.json"
    image_path = directory / "original-flash.bin"
    if not manifest_path.is_file() or not image_path.is_file():
        raise FirmwareTrustError("stock backup requires manifest.json and original-flash.bin")
    meta = _load_json(manifest_path)
    target = expected_target_id or profile.target_id
    if meta.get("target_id") != target or target != profile.target_id:
        raise FirmwareTrustError("stock backup target mismatch")
    if meta.get("flash_size_bytes") != profile.stock_flash_size_bytes:
        raise FirmwareTrustError("stock backup flash geometry mismatch")
    if meta.get("read_passes") != 2 or meta.get("two_pass_byte_identical") is not True:
        raise FirmwareTrustError("stock backup lacks verified two-pass identity")
    if meta.get("stock_sha256_match") is not True:
        raise FirmwareTrustError("stock backup did not match the golden stock SHA256")
    if meta.get("option_bytes_read_or_written") not in (False, None):
        raise FirmwareTrustError("stock backup touched option bytes")
    if meta.get("flash_written") not in (False, None):
        raise FirmwareTrustError("backup manifest unexpectedly records a flash write")
    if image_path.stat().st_size != profile.stock_flash_size_bytes:
        raise FirmwareTrustError("stock backup image size mismatch")
    digest = _sha256(image_path)
    if digest != profile.stock_flash_sha256:
        raise FirmwareTrustError("stock backup image SHA256 mismatch")
    if str(meta.get("sha256", "")).lower() != digest:
        raise FirmwareTrustError("stock backup manifest SHA256 mismatch")
    return digest


def verify_programmed_readback(
    profile: ProductFirmwareProfile,
    readback: str | Path,
) -> str:
    path = Path(readback)
    if not path.is_file():
        raise FirmwareTrustError(f"programmed readback not found: {path}")
    if path.stat().st_size != profile.programmed_readback_bytes:
        raise FirmwareTrustError("programmed readback size mismatch")
    digest = _sha256(path)
    if digest != profile.programmed_readback_sha256:
        raise FirmwareTrustError(
            f"programmed readback SHA256 mismatch: expected {profile.programmed_readback_sha256}, got {digest}"
        )
    return digest


def write_service_eligibility(
    *,
    profile: ProductFirmwareProfile,
    config: str | Path,
    firmware: str | Path,
    readback_sha256: str,
    runtime_identity: str,
    stock_backup_dir: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    readiness = inspect_runtime_readiness(config)
    if readiness.status != READY:
        raise FirmwareTrustError(
            f"runtime configuration is not READY: {readiness.status}:{','.join(readiness.reasons)}"
        )
    artifact_sha = verify_artifact(profile, firmware)
    backup_sha = verify_stock_backup(profile, stock_backup_dir)
    if readback_sha256.lower() != profile.programmed_readback_sha256:
        raise FirmwareTrustError("reported programmed-readback SHA256 is not the qualified artifact SHA256")
    if runtime_identity != profile.expected_identity:
        raise FirmwareTrustError("runtime identity does not exactly match qualified AX25R4 identity")

    record = {
        "schema": 1,
        "product": "YWD-1278",
        "series": "AX25R4",
        "status": "SERVICE-ELIGIBLE",
        "target_id": profile.target_id,
        "artifact_sha256": artifact_sha,
        "programmed_readback_sha256": readback_sha256.lower(),
        "runtime_identity": runtime_identity,
        "stock_backup_sha256": backup_sha,
        "stock_backup_dir": str(Path(stock_backup_dir)),
        "runtime_readiness": READY,
        "tx_enabled": False,
        "automatic_flash_enabled": False,
        "option_bytes_written": False,
        "service_enabled_by_stage_f": False,
        "created_unix": int(time.time()),
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def verify_service_eligibility(
    *,
    profile: ProductFirmwareProfile,
    config: str | Path,
    firmware: str | Path,
    record_path: str | Path,
) -> dict[str, Any]:
    record = _load_json(Path(record_path))
    if record.get("schema") != 1 or record.get("status") != "SERVICE-ELIGIBLE":
        raise FirmwareTrustError("invalid service eligibility record")
    if record.get("target_id") != profile.target_id:
        raise FirmwareTrustError("service eligibility target mismatch")
    if record.get("runtime_identity") != profile.expected_identity:
        raise FirmwareTrustError("service eligibility runtime identity mismatch")
    if record.get("artifact_sha256") != profile.artifact_sha256:
        raise FirmwareTrustError("service eligibility artifact mismatch")
    if record.get("programmed_readback_sha256") != profile.programmed_readback_sha256:
        raise FirmwareTrustError("service eligibility readback mismatch")
    if record.get("tx_enabled") is not False or record.get("automatic_flash_enabled") is not False:
        raise FirmwareTrustError("service eligibility record violates no-TX/no-auto-flash policy")
    if record.get("option_bytes_written") is not False:
        raise FirmwareTrustError("service eligibility record reports option-byte writes")
    if record.get("service_enabled_by_stage_f") is not False:
        raise FirmwareTrustError("Stage F eligibility record must not claim service activation")
    readiness = inspect_runtime_readiness(config)
    if readiness.status != READY:
        raise FirmwareTrustError("configuration is no longer READY")
    verify_artifact(profile, firmware)
    backup_dir = record.get("stock_backup_dir")
    if not isinstance(backup_dir, str) or not backup_dir:
        raise FirmwareTrustError("service eligibility record has no stock backup path")
    verify_stock_backup(profile, backup_dir)
    return record


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="python -m ywd1278.install.firmware_trust")
    parser.add_argument("--profile", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_art = sub.add_parser("artifact")
    p_art.add_argument("--firmware", required=True)

    p_backup = sub.add_parser("backup")
    p_backup.add_argument("--backup-dir", required=True)

    p_readback = sub.add_parser("readback")
    p_readback.add_argument("--readback", required=True)

    p_write = sub.add_parser("write-eligibility")
    p_write.add_argument("--config", required=True)
    p_write.add_argument("--firmware", required=True)
    p_write.add_argument("--readback-sha256", required=True)
    p_write.add_argument("--runtime-identity", required=True)
    p_write.add_argument("--stock-backup-dir", required=True)
    p_write.add_argument("--output", required=True)

    p_check = sub.add_parser("check-eligibility")
    p_check.add_argument("--config", required=True)
    p_check.add_argument("--firmware", required=True)
    p_check.add_argument("--record", required=True)

    args = parser.parse_args()
    try:
        profile = load_product_firmware_profile(args.profile)
        if args.command == "artifact":
            digest = verify_artifact(profile, args.firmware)
            print("YWD1278_PRODUCT_FIRMWARE_ARTIFACT=PASS")
            print(f"ARTIFACT_SHA256={digest}")
            print(f"ARTIFACT_SIZE_BYTES={profile.artifact_size_bytes}")
        elif args.command == "backup":
            digest = verify_stock_backup(profile, args.backup_dir)
            print("YWD1278_STOCK_BACKUP_TRUST=PASS")
            print(f"STOCK_BACKUP_SHA256={digest}")
            print("BACKUP_READ_PASSES=2")
            print("OPTION_BYTES_READ_OR_WRITTEN=NO")
        elif args.command == "readback":
            digest = verify_programmed_readback(profile, args.readback)
            print("YWD1278_PROGRAMMED_READBACK=PASS")
            print(f"PROGRAMMED_READBACK_SHA256={digest}")
        elif args.command == "write-eligibility":
            record = write_service_eligibility(
                profile=profile,
                config=args.config,
                firmware=args.firmware,
                readback_sha256=args.readback_sha256,
                runtime_identity=args.runtime_identity,
                stock_backup_dir=args.stock_backup_dir,
                output=args.output,
            )
            print("YWD1278_SERVICE_ELIGIBILITY=PASS")
            print(f"ELIGIBILITY_RECORD={args.output}")
            print(f"RUNTIME_IDENTITY={record['runtime_identity']}")
            print("SERVICE_ENABLED=NO")
        elif args.command == "check-eligibility":
            verify_service_eligibility(
                profile=profile,
                config=args.config,
                firmware=args.firmware,
                record_path=args.record,
            )
            print("YWD1278_SERVICE_ELIGIBILITY_CHECK=PASS")
            print("SERVICE_ELIGIBLE=YES")
            print("SERVICE_ENABLED=NO")
    except FirmwareTrustError as exc:
        print(f"YWD1278_FIRMWARE_TRUST=FAIL:{exc}")
        return 20
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
