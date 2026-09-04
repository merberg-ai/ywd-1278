#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-firmware-build-failure-target-pi.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "H"
    assert d["status"] == "target-pi-firmware-build-blocked-toolchain-headers-missing"
    assert d["hat_firmware_class_before_build"] == "STOCK"
    assert d["build_attempt"]["exit_code"] == 1
    assert d["build_attempt"]["missing_c_header"] == "string.h"
    assert d["build_attempt"]["missing_cpp_header"] == "cstdint"
    assert d["build_attempt"]["artifact_produced"] is False
    assert d["root_cause"]["class"] == "installer-package-dependency-gap"
    safety = d["safety"]
    assert safety["modem_uart_opened_by_build"] is False
    assert safety["hat_gpio_accessed_by_build"] is False
    assert safety["flash_written"] is False
    assert safety["option_bytes_written"] is False
    assert safety["rf_transmitted"] is False
    assert safety["packet_service_enabled"] is False
    assert safety["tx_enabled"] is False
    assert d["qualification_effect"]["stage_h_complete"] is False
    print("YWD1278_STAGE_H_FIRMWARE_BUILD_FAILURE_EVIDENCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
