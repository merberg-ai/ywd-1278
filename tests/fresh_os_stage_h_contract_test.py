#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_STAGE_G_FINAL = {
    "firmware/qualification/0b-product-existing-pi-stage-g-reboot-target-pi.json": "e5adfac10e30ef3540dd8af14d51666915642c4d",
    "tests/existing_pi_stage_g_reboot_evidence_contract_test.py": "9d698e55d6fdccfd5591b9957efc3562bd200450",
    "docs/qualifications/fresh-install-stage-g-existing-pi-reboot-qualified-2026-09-04.md": "47351dfbd6369d56e6b5b06d4070f18b31fca53a",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    for path, expected in FROZEN_STAGE_G_FINAL.items():
        actual = blob(path)
        assert actual == expected, f"frozen Stage-G final evidence drift: {path}: {actual} != {expected}"

    preflight = (ROOT / "tools/stage_h_fresh_os_preflight.sh").read_text(encoding="utf-8")
    for required in (
        "/opt/ywd-1278",
        "/etc/ywd-1278",
        "/var/lib/ywd-1278",
        "PREEXISTING_YWD1278_STATE=NO",
        "installer/platform.sh\" audit",
        "PRE_INSTALL_HAT_IDENTITY_CAPTURED",
        "YWD1278_STAGE_H_FRESH_OS_PREFLIGHT=PASS",
        "PLATFORM_MUTATED=NO",
        "SERVICE_ENABLED=NO",
        "FLASH_WRITTEN=NO",
        "RF_TRANSMITTED=NO",
    ):
        assert required in preflight, f"Stage-H preflight missing token: {required}"

    for forbidden in (
        "platform.sh\" apply",
        "systemctl enable",
        "systemctl start",
        "systemctl restart",
        "systemctl reboot",
        "stm32flash",
        "deploy-product-firmware",
        "WRITE-FIRMWARE-NOW",
        "FLASH-QUALIFIED-AX25R4",
        "TX_ACCEPT",
        "tx_enabled = true",
    ):
        assert forbidden not in preflight, f"Stage-H preflight gained forbidden capability: {forbidden}"

    install = (ROOT / "installer/install.sh").read_text(encoding="utf-8")
    resume = (ROOT / "installer/resume.sh").read_text(encoding="utf-8")
    toolchain = (ROOT / "installer/firmware-toolchain-check.sh").read_text(encoding="utf-8")
    for text, name in ((install, "install"), (resume, "resume")):
        assert "SERVICE_ENABLED=NO" in text, name
        assert "RF_TRANSMITTED=NO" in text, name
        assert "FLASH_WRITTEN=NO" in text, name
    assert "systemctl enable ywd-1278-install-resume.service" in install
    assert "systemctl reboot" in install
    assert "YWD1278_INSTALL_RESUME=PASS" in resume
    assert "SERIAL_CONSOLE_PRESENT=NO" in resume
    assert "RUNTIME_UART_READY=YES" in resume

    for token in (
        "libnewlib-arm-none-eabi",
        "libstdc++-arm-none-eabi-dev",
        "libstdc++-arm-none-eabi-newlib",
        "psmisc",
        "firmware-toolchain-check.sh\" check",
    ):
        assert token in install, f"fresh installer missing firmware dependency/toolchain gate: {token}"

    for token in (
        "#include <stdint.h>",
        "#include <string.h>",
        "#include <cstdint>",
        "#include <cstring>",
        "arm-none-eabi-gcc",
        "arm-none-eabi-g++",
        "YWD1278_FIRMWARE_TOOLCHAIN_CHECK=PASS",
        "HARDWARE_ACCESS=NO",
        "FLASH_WRITTEN=NO",
        "RF_TRANSMITTED=NO",
    ):
        assert token in toolchain, f"toolchain smoke check missing token: {token}"
    for forbidden in ("/dev/tty", "hat_control", "stm32flash -w", "TX_ACCEPT"):
        assert forbidden not in toolchain, f"toolchain check gained hardware/write capability: {forbidden}"

    print("YWD1278_STAGE_H_FRESH_OS_CONTRACT=PASS")
    print("FROZEN_STAGE_G_FINAL_EVIDENCE=PASS")
    print("FRESH_OS_PREINSTALL_STATE_REQUIRED=EMPTY")
    print("PREFLIGHT_PLATFORM_MUTATION=ABSENT")
    print("PREFLIGHT_FIRMWARE_WRITE=ABSENT")
    print("PREFLIGHT_RF_TX=ABSENT")
    print("INSTALLER_UART_REPAIR_RESUME_PATH=REQUIRED")
    print("FIRMWARE_TOOLCHAIN_HEADERS_REQUIRED=YES")
    print("PACKET_SERVICE_ENABLE_DURING_INSTALL=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
