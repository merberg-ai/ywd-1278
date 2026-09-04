#!/usr/bin/env python3
"""Contract for Stage-H target-Pi deterministic product-firmware build success evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-firmware-build-success-target-pi.json"
EXPECTED_SHA256 = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_IDENTITY = "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["stage"] == "H"
    assert data["status"] == "target-pi-firmware-build-qualified-after-toolchain-remediation"
    assert data["remediation_checkpoint"] == {
        "branch": "checkpoint/product-fresh-os-stage-h-toolchain-remediation-host-qualified",
        "sha": "2f5299e65add072fea6ee55a54dc421faf00c276",
        "host_ci_run_id": 33926348174,
        "host_ci_conclusion": "success",
    }

    build = data["build"]
    assert build["exit_code"] == 0
    assert build["putty_session_survived"] is True
    assert build["reproducible_builds"] == "PASS"
    assert build["rssi_firmware_build"] == "PASS"
    assert build["product_firmware_artifact"] == "PASS"
    assert build["product_firmware_prepare"] == "PASS"
    assert build["artifact_size_bytes"] == 59892
    assert build["artifact_sha256"] == EXPECTED_SHA256
    assert build["expected_artifact_sha256"] == EXPECTED_SHA256
    assert build["artifact_identity"] == EXPECTED_IDENTITY
    assert build["artifact_identity_count"] == 1
    assert build["vector_initial_sp"] == "0x20005000"
    assert build["vector_reset"] == "0x080080ad"
    assert build["rssi_subcommand"] == "0x05"
    assert build["rssi_threshold_selected"] is False
    assert build["engineering_external_repo_required"] is False

    assert data["safety"] == {
        "hardware_access": False,
        "modem_uart_opened": False,
        "rf_configured": False,
        "rf_transmitted": False,
        "flash_written": False,
        "option_bytes_written": False,
    }
    claims = data["qualified_claims"]
    for key in (
        "fresh_pi_can_build_frozen_product_ax25r4_artifact",
        "artifact_matches_frozen_product_size",
        "artifact_matches_frozen_product_sha256",
        "artifact_matches_frozen_product_identity",
        "build_is_reproducible",
        "toolchain_header_failure_remediated",
    ):
        assert claims[key] is True
    assert claims["physical_tx"] is False
    assert claims["flash_write"] is False
    assert claims["option_byte_write"] is False

    print("YWD1278_STAGE_H_FRESH_PI_FIRMWARE_BUILD_EVIDENCE=PASS")
    print(f"ARTIFACT_SHA256={EXPECTED_SHA256}")
    print("ARTIFACT_SIZE_BYTES=59892")
    print("REPRODUCIBLE_BUILDS=PASS")
    print("HARDWARE_ACCESS=NO")
    print("FLASH_WRITTEN=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
