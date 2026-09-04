#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-preinstall-target-pi.json"

FROZEN = {
    "tools/stage_h_fresh_os_preflight.sh": "d2a31979f4a134e7a4636519b3eabfc89c3aa27f",
    "installer/platform.sh": "db62d5d4682df163691bcfbb7e8f659867f10b0c",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    for path, expected in FROZEN.items():
        actual = blob(path)
        assert actual == expected, f"Stage-H preinstall boundary drift: {path}: {actual} != {expected}"

    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1 and d["stage"] == "H"
    assert d["status"] == "target-pi-preinstall-qualified-installer-pending"
    assert d["checkout_sha"] == "9d1b2b521e30d6d3b0cb0de002cd385b631451da"
    assert d["parent_stage_g_sha"] == "1e2ecb162fdd900ca80b8e69ca085f8d591e7aab"

    t = d["target"]
    assert t["model"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert t["os"] == "Debian GNU/Linux 13 (trixie)"
    assert t["kernel"] == "6.18.34+rpt-rpi-2712"
    assert t["arch"] == "aarch64"
    assert t["boot_id"] == "9a99d5cd-5940-4832-a292-2d0850e5ab09"

    assert d["freshness"]["preexisting_ywd1278_state"] is False
    assert d["freshness"]["preexisting_ywd1278_service"] is False

    u = d["uart_audit"]
    assert u["runtime_uart_ready"] is False
    assert u["serial_console_present"] is True
    assert u["reboot_required"] is True
    assert u["reboot_reasons"] == ["uart-not-ready", "serial-console"]

    h = d["preinstall_hat_identity"]
    assert h["captured"] is False
    assert h["reason"] == "UART_REPAIR_REQUIRED"

    s = d["safety"]
    assert s == {
        "platform_mutated": False,
        "service_enabled": False,
        "flash_written": False,
        "rf_transmitted": False,
    }

    q = d["qualified_claims"]
    assert q["fresh_os_baseline"] is True
    assert q["installer_uart_repair_path_required"] is True
    assert q["installer_reboot_resume_path_required"] is True
    assert q["hat_firmware_preinstall_identity_known"] is False
    assert q["physical_tx"] is False
    assert q["flash_write"] is False

    print("YWD1278_STAGE_H_PREINSTALL_TARGET_PI_EVIDENCE=PASS")
    print("FRESH_OS_BASELINE=PASS")
    print("UART_REPAIR_REQUIRED=YES")
    print("SERIAL_CONSOLE_PRESENT=YES")
    print("INSTALLER_REBOOT_RESUME_REQUIRED=YES")
    print("PREINSTALL_HAT_IDENTITY=UNKNOWN_UART_BLOCKED")
    print("FLASH_WRITE=NO")
    print("PHYSICAL_TX=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
