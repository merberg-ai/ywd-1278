"""File-only trust bridge between HAT setup and final runtime activation.

The qualified firmware deployment can happen before the operator enters a
callsign, packet frequency, or console/BBS settings.  This module records only
facts about the hardware/firmware operation.  It performs no UART, GPIO,
systemd, programmer, or RF I/O.

A HARDWARE-QUALIFIED record is deliberately *not* service eligibility.  After
station configuration is complete, ``promote`` revalidates the hardware record
and delegates to the existing firmware_trust service-eligibility function,
which still requires full runtime readiness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from ywd1278.install.firmware_trust import (
    FirmwareTrustError,
    ProductFirmwareProfile,
    load_product_firmware_profile,
    verify_artifact,
    verify_stock_backup,
    write_service_eligibility,
)

HARDWARE_STATUS = "HARDWARE-QUALIFIED"
HARDWARE_SCHEMA = 1


def _load_record(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirmwareTrustError(f"cannot load hardware trust record {p}: {exc}") from exc
    if not isinstance(value, dict):
        raise FirmwareTrustError("hardware trust record root must be an object")
    return value


def write_hardware_qualification(
    *,
    profile: ProductFirmwareProfile,
    firmware: str | Path,
    programmed_readback_sha256: str,
    runtime_identity: str,
    stock_backup_dir: str | Path,
    flash_written: bool,
    output: str | Path,
) -> dict[str, Any]:
    """Write a no-runtime-config hardware/firmware qualification record."""

    artifact_sha = verify_artifact(profile, firmware)
    backup_sha = verify_stock_backup(profile, stock_backup_dir)
    readback_sha = programmed_readback_sha256.lower()
    if readback_sha != profile.programmed_readback_sha256:
        raise FirmwareTrustError("reported programmed-readback SHA256 is not the qualified artifact SHA256")
    if runtime_identity != profile.expected_identity:
        raise FirmwareTrustError("runtime identity does not exactly match qualified AX25R4 identity")
    if not isinstance(flash_written, bool):
        raise FirmwareTrustError("flash_written must be boolean")

    record: dict[str, Any] = {
        "schema": HARDWARE_SCHEMA,
        "product": "YWD-1278",
        "series": "AX25R4",
        "status": HARDWARE_STATUS,
        "target_id": profile.target_id,
        "artifact_sha256": artifact_sha,
        "programmed_readback_sha256": readback_sha,
        "runtime_identity": runtime_identity,
        "stock_backup_sha256": backup_sha,
        "stock_backup_dir": str(Path(stock_backup_dir)),
        "flash_written_during_setup": flash_written,
        "option_bytes_written": False,
        "service_enabled": False,
        "rf_transmitted": False,
        "runtime_configuration_required_for_service": True,
        "created_unix": int(time.time()),
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def verify_hardware_qualification(
    *,
    profile: ProductFirmwareProfile,
    firmware: str | Path,
    record_path: str | Path,
) -> dict[str, Any]:
    """Revalidate a HARDWARE-QUALIFIED record without touching hardware."""

    record = _load_record(record_path)
    if record.get("schema") != HARDWARE_SCHEMA or record.get("status") != HARDWARE_STATUS:
        raise FirmwareTrustError("invalid hardware qualification record")
    if record.get("product") != "YWD-1278" or record.get("series") != "AX25R4":
        raise FirmwareTrustError("hardware qualification product mismatch")
    if record.get("target_id") != profile.target_id:
        raise FirmwareTrustError("hardware qualification target mismatch")
    if record.get("artifact_sha256") != profile.artifact_sha256:
        raise FirmwareTrustError("hardware qualification artifact mismatch")
    if record.get("programmed_readback_sha256") != profile.programmed_readback_sha256:
        raise FirmwareTrustError("hardware qualification readback mismatch")
    if record.get("runtime_identity") != profile.expected_identity:
        raise FirmwareTrustError("hardware qualification runtime identity mismatch")
    if record.get("option_bytes_written") is not False:
        raise FirmwareTrustError("hardware qualification reports option-byte writes")
    if record.get("service_enabled") is not False:
        raise FirmwareTrustError("hardware qualification must precede service activation")
    if record.get("rf_transmitted") is not False:
        raise FirmwareTrustError("hardware qualification unexpectedly reports RF transmission")
    if record.get("runtime_configuration_required_for_service") is not True:
        raise FirmwareTrustError("hardware qualification incorrectly claims runtime readiness")
    if not isinstance(record.get("flash_written_during_setup"), bool):
        raise FirmwareTrustError("hardware qualification flash-written field is invalid")

    verify_artifact(profile, firmware)
    backup_dir = record.get("stock_backup_dir")
    if not isinstance(backup_dir, str) or not backup_dir:
        raise FirmwareTrustError("hardware qualification record has no stock backup path")
    backup_sha = verify_stock_backup(profile, backup_dir)
    if record.get("stock_backup_sha256") != backup_sha:
        raise FirmwareTrustError("hardware qualification stock backup digest mismatch")
    return record


def promote_to_service_eligibility(
    *,
    profile: ProductFirmwareProfile,
    config: str | Path,
    firmware: str | Path,
    hardware_record: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    """Promote verified HAT evidence after the final runtime config is READY."""

    record = verify_hardware_qualification(
        profile=profile,
        firmware=firmware,
        record_path=hardware_record,
    )
    return write_service_eligibility(
        profile=profile,
        config=config,
        firmware=firmware,
        readback_sha256=str(record["programmed_readback_sha256"]),
        runtime_identity=str(record["runtime_identity"]),
        stock_backup_dir=str(record["stock_backup_dir"]),
        output=output,
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="python -m ywd1278.install.hardware_trust")
    parser.add_argument("--profile", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_write = sub.add_parser("write-hardware")
    p_write.add_argument("--firmware", required=True)
    p_write.add_argument("--readback-sha256", required=True)
    p_write.add_argument("--runtime-identity", required=True)
    p_write.add_argument("--stock-backup-dir", required=True)
    p_write.add_argument("--flash-written", choices=("yes", "no"), required=True)
    p_write.add_argument("--output", required=True)

    p_check = sub.add_parser("check-hardware")
    p_check.add_argument("--firmware", required=True)
    p_check.add_argument("--record", required=True)

    p_promote = sub.add_parser("promote")
    p_promote.add_argument("--config", required=True)
    p_promote.add_argument("--firmware", required=True)
    p_promote.add_argument("--record", required=True)
    p_promote.add_argument("--output", required=True)

    args = parser.parse_args()
    try:
        profile = load_product_firmware_profile(args.profile)
        if args.command == "write-hardware":
            record = write_hardware_qualification(
                profile=profile,
                firmware=args.firmware,
                programmed_readback_sha256=args.readback_sha256,
                runtime_identity=args.runtime_identity,
                stock_backup_dir=args.stock_backup_dir,
                flash_written=args.flash_written == "yes",
                output=args.output,
            )
            print("YWD1278_HARDWARE_QUALIFICATION=PASS")
            print(f"HARDWARE_RECORD={args.output}")
            print(f"TARGET_ID={record['target_id']}")
            print("SERVICE_ELIGIBLE=NO")
        elif args.command == "check-hardware":
            verify_hardware_qualification(
                profile=profile,
                firmware=args.firmware,
                record_path=args.record,
            )
            print("YWD1278_HARDWARE_QUALIFICATION_CHECK=PASS")
            print("HAT_READY=YES")
            print("SERVICE_ELIGIBLE=NO")
        elif args.command == "promote":
            promote_to_service_eligibility(
                profile=profile,
                config=args.config,
                firmware=args.firmware,
                hardware_record=args.record,
                output=args.output,
            )
            print("YWD1278_HARDWARE_PROMOTION=PASS")
            print(f"ELIGIBILITY_RECORD={args.output}")
            print("SERVICE_ELIGIBLE=YES")
    except FirmwareTrustError as exc:
        print(f"YWD1278_HARDWARE_TRUST=FAIL:{exc}")
        return 20

    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    return 0


def main() -> int:
    return _cli()


if __name__ == "__main__":
    raise SystemExit(main())
