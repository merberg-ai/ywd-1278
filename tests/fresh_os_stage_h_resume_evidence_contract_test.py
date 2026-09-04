#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-resume-target-pi.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "H"
    assert d["status"] == "target-pi-installer-resume-qualified"

    pre = d["preinstall"]
    assert pre["boot_id"] == "9a99d5cd-5940-4832-a292-2d0850e5ab09"
    assert pre["runtime_uart_ready"] is False
    assert pre["serial_console_present"] is True
    assert pre["reboot_required"] is True
    assert pre["preexisting_ywd1278_state"] is False
    assert pre["preexisting_ywd1278_service"] is False

    product = d["installed_product"]
    assert product["installed_commit"] == "3ab12069fc6080f41f3c511c8525ba6ccd92175b"
    assert product["hardware_target"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
    assert product["uart"] == "/dev/ttyAMA0"
    assert product["frequency_hz"] == 145050000
    assert product["kiss_host"] == "127.0.0.1" and product["kiss_port"] == 8001
    assert product["console_host"] == "127.0.0.1" and product["console_port"] == 8010
    assert product["pty_link"] == "/run/ywd-1278/tnc"
    assert product["tx_enabled"] is False
    assert product["automatic_flash_enabled"] is False

    post = d["post_reboot"]
    assert post["boot_id"] == "79055777-d228-4c3d-9b74-dc27cd322297"
    assert post["boot_id"] != pre["boot_id"]
    assert post["boot_id_changed_from_preinstall"] is True
    assert post["runtime_uart_ready"] is True
    assert post["serial_console_present"] is False
    assert post["reboot_required"] is False
    assert post["resume_service_completed"] is True
    assert post["resume_service_final_state"] == "inactive"
    assert post["resume_service_disabled"] is True
    assert post["runtime_config_ready"] is True
    assert post["packet_service_enabled"] is False
    assert post["packet_service_active"] is False

    hat = d["hat_detection"]
    assert hat["result"] == "pass"
    assert hat["target"] == product["hardware_target"]
    assert hat["identity"] == "MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed"
    assert hat["firmware_class"] == "STOCK"
    assert hat["application_release_used"] is False
    assert hat["rf_configured"] is False
    assert hat["flash_written"] is False
    assert hat["option_bytes_written"] is False

    claims = d["qualified_claims"]
    for key in (
        "fresh_os_preinstall_baseline",
        "normal_installer_ran",
        "uart_repair_required_and_applied",
        "actual_reboot_occurred",
        "automatic_resume_completed",
        "uart_runtime_ready_after_reboot",
        "serial_console_removed",
        "supported_hat_detected_after_reboot",
        "stock_firmware_detected_after_reboot",
        "hardware_target_bound",
        "runtime_readiness_ready",
        "packet_service_remained_disabled",
    ):
        assert claims[key] is True, key
    assert claims["physical_tx"] is False
    assert claims["flash_write"] is False

    print("YWD1278_STAGE_H_INSTALLER_RESUME_TARGET_PI_EVIDENCE=PASS")
    print("ACTUAL_REBOOT=PASS")
    print("UART_REPAIR_RESUME=PASS")
    print("STOCK_HAT_IDENTITY=PASS")
    print("RUNTIME_READINESS=READY")
    print("SERVICE_ENABLED=NO")
    print("PHYSICAL_TX=NO")
    print("FLASH_WRITE=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
