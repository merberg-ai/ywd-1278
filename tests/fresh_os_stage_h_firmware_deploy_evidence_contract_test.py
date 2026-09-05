#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-firmware-deploy-target-pi.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "H"
    assert d["status"] == "target-pi-firmware-deployment-qualified"

    assert d["target"]["id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
    assert d["target"]["pre_write_firmware_class"] == "STOCK"
    assert d["target"]["post_write_firmware_class"] == "YWD1278"
    assert d["target"]["bootloader_version"] == "0x22"
    assert d["target"]["device_id"] == "0x0410"

    expected = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
    assert d["artifact"]["size_bytes"] == 59892
    assert d["artifact"]["sha256"] == expected
    assert d["write"]["main_flash_write_occurred"] is True
    assert d["write"]["programmer_write_verify_passed"] is True
    assert d["write"]["programmed_readback_bytes"] == 59892
    assert d["write"]["programmed_readback_sha256"] == expected
    assert d["write"]["programmed_readback_passed"] is True
    assert d["write"]["exact_runtime_identity_verified"] is True
    assert d["write"]["option_bytes_written"] is False

    stock = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
    assert d["deployment_backup"]["flash_size_bytes"] == 131072
    assert d["deployment_backup"]["sha256"] == stock
    assert d["deployment_backup"]["read_passes"] == 2
    assert d["deployment_backup"]["two_pass_byte_identical"] is True
    assert d["deployment_backup"]["stock_golden_sha256_match"] is True
    assert d["deployment_backup"]["option_bytes_read"] is False

    assert d["service_eligibility"]["write_passed"] is True
    assert d["service_eligibility"]["validation_passed"] is True
    assert d["service_eligibility"]["service_eligible"] is True
    assert d["service_eligibility"]["service_enabled"] is False

    assert d["safety"] == {
        "runtime_readiness_ready": True,
        "tx_enabled": False,
        "automatic_flash_enabled": False,
        "rf_transmitted": False,
        "packet_service_enabled": False,
        "packet_service_active": False,
        "option_bytes_written": False,
    }
    assert d["qualified_claims"]["physical_tx"] is False
    assert d["qualified_claims"]["service_activation"] is False
    print("YWD1278_STAGE_H_FRESH_OS_FIRMWARE_DEPLOY_EVIDENCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
