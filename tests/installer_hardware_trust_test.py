#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from ywd1278.install.firmware_trust import FirmwareTrustError, load_product_firmware_profile
from ywd1278.install.hardware_trust import (
    promote_to_service_eligibility,
    verify_hardware_qualification,
    write_hardware_qualification,
)

ROOT = Path(__file__).resolve().parents[1]
TARGET = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
IDENTITY = "TEST-YWD-1278-AX25R4"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    firmware_bytes = b"qualified-test-artifact\n"
    stock_bytes = b"stock-image-for-test\n"
    firmware = root / "firmware.bin"
    firmware.write_bytes(firmware_bytes)

    backup = root / "backup"
    backup.mkdir()
    (backup / "original-flash.bin").write_bytes(stock_bytes)
    (backup / "manifest.json").write_text(
        json.dumps(
            {
                "target_id": TARGET,
                "flash_size_bytes": len(stock_bytes),
                "read_passes": 2,
                "two_pass_byte_identical": True,
                "stock_sha256_match": True,
                "option_bytes_read_or_written": False,
                "flash_written": False,
                "sha256": sha(stock_bytes),
            }
        ),
        encoding="utf-8",
    )

    profile_path = root / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "product": "YWD-1278",
                "series": "AX25R4",
                "target_id": TARGET,
                "expected_identity": IDENTITY,
                "artifact_relative_path": "firmware.bin",
                "artifact_size_bytes": len(firmware_bytes),
                "artifact_sha256": sha(firmware_bytes),
                "flash_base": "0x08000000",
                "programmed_readback_bytes": len(firmware_bytes),
                "programmed_readback_sha256": sha(firmware_bytes),
                "stock_flash_size_bytes": len(stock_bytes),
                "stock_flash_sha256": sha(stock_bytes),
                "expected_bootloader_version": "0x22",
                "expected_device_id": "0x0410",
                "flash_authorization_token": "FLASH-QUALIFIED-AX25R4",
                "service_eligibility_record": str(root / "service-ready.json"),
                "safety": {
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
                },
            }
        ),
        encoding="utf-8",
    )
    profile = load_product_firmware_profile(profile_path)

    hardware_record = root / "hardware-ready.json"
    written = write_hardware_qualification(
        profile=profile,
        firmware=firmware,
        programmed_readback_sha256=sha(firmware_bytes),
        runtime_identity=IDENTITY,
        stock_backup_dir=backup,
        flash_written=True,
        output=hardware_record,
    )
    assert written["status"] == "HARDWARE-QUALIFIED"
    assert written["service_enabled"] is False
    assert written["rf_transmitted"] is False
    assert written["runtime_configuration_required_for_service"] is True
    assert written["flash_written_during_setup"] is True

    checked = verify_hardware_qualification(
        profile=profile,
        firmware=firmware,
        record_path=hardware_record,
    )
    assert checked["programmed_readback_sha256"] == sha(firmware_bytes)

    # Hardware qualification deliberately succeeds before callsign/frequency
    # configuration exists. Promotion, however, still requires the existing
    # full runtime-readiness authority.
    incomplete_config = root / "incomplete.toml"
    incomplete_config.write_text((ROOT / "config/ywd-1278.example.toml").read_text(encoding="utf-8"), encoding="utf-8")
    try:
        promote_to_service_eligibility(
            profile=profile,
            config=incomplete_config,
            firmware=firmware,
            hardware_record=hardware_record,
            output=root / "should-not-exist.json",
        )
    except FirmwareTrustError:
        pass
    else:
        raise AssertionError("incomplete runtime config unexpectedly promoted hardware evidence")

    ready_text = incomplete_config.read_text(encoding="utf-8")
    ready_text = ready_text.replace('callsign = "N0CALL"', 'callsign = "KJ6YWD"')
    ready_text = ready_text.replace('target = ""', f'target = "{TARGET}"')
    ready_text = ready_text.replace('frequency_mhz = 0.0', 'frequency_mhz = 145.050')
    ready_config = root / "ready.toml"
    ready_config.write_text(ready_text, encoding="utf-8")

    service_record = root / "service-ready.json"
    promoted = promote_to_service_eligibility(
        profile=profile,
        config=ready_config,
        firmware=firmware,
        hardware_record=hardware_record,
        output=service_record,
    )
    assert promoted["status"] == "SERVICE-ELIGIBLE"
    assert promoted["runtime_readiness"] == "READY"
    assert promoted["stock_backup_dir"] == str(backup)

    # Tampering with the pre-config hardware record must fail closed.
    tampered = json.loads(hardware_record.read_text(encoding="utf-8"))
    tampered["runtime_identity"] = "WRONG"
    hardware_record.write_text(json.dumps(tampered), encoding="utf-8")
    try:
        verify_hardware_qualification(profile=profile, firmware=firmware, record_path=hardware_record)
    except FirmwareTrustError:
        pass
    else:
        raise AssertionError("tampered hardware qualification record was accepted")

print("INSTALLER_HARDWARE_TRUST=PASS")
print("HARDWARE_BEFORE_RUNTIME_CONFIG=PASS")
print("SERVICE_PROMOTION_REQUIRES_RUNTIME_READY=PASS")
print("NO_HARDWARE_IO=PASS")
