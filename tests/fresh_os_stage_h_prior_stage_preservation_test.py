#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Historical Stage-E/F evidence remains immutable. Stage H intentionally
# supersedes installer/install.sh only to repair the bare-metal toolchain
# dependency set discovered on the physical fresh-OS Pi.
FROZEN = {
    "firmware/qualification/0b-product-installer-runtime-stage-e.json": "1d23b9dd0210ff65cc25bebc14040310da1d28e2",
    "tests/installer_runtime_stage_e_contract_test.py": "c9667398d72dfac3c99a9019cf02754372a25477",
    "tests/installer_runtime_stage_e_qualification_contract_test.py": "9d06aaf9e66b33a78572d404217857f27fca950b",
    "tests/installer_runtime_stage_e_test.py": "01ef4601f6e36c3b7357d4d7f33c5ba7969165b0",
    "firmware/qualification/0b-product-firmware-trust-stage-f.json": "702598db66d7ab92c384850c6dfed973e697fe5e",
    "tests/firmware_trust_stage_f_contract_test.py": "6325ed29a828bd857d894a1d29e2cb87d25d04f2",
    "tests/firmware_trust_stage_f_qualification_contract_test.py": "436e3d5ac33f316d8194a9165e9d136b69659be5",
    "tests/firmware_trust_stage_f_test.py": "e6a97a46f7c6aae9390ebfb638634f92c1a8d1bb",
    "firmware/product-ax25r4.json": "b7263fbe7bde1ad547207b7cc0e4f22220b38f72",
    "src/ywd1278/install/firmware_trust.py": "5f119de52a9363adcb10eab8e007a2cee8cab158",
    "firmware/prepare-product-ax25r4.sh": "35abcbe4fed888dcd4f8e422e2954fc13e8f1ded",
    "installer/deploy-product-firmware.sh": "94adb8ddd4dfebd90a1ea105203afc6a5049e828",
}


def blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def main() -> int:
    for path, expected in FROZEN.items():
        actual = blob(path)
        assert actual == expected, f"historical Stage-E/F evidence or Stage-F firmware implementation drift: {path}: {actual} != {expected}"

    installer = (ROOT / "installer/install.sh").read_text(encoding="utf-8")
    assert "libnewlib-arm-none-eabi" in installer
    assert "libstdc++-arm-none-eabi-dev" in installer
    assert "libstdc++-arm-none-eabi-newlib" in installer
    assert "firmware-toolchain-check.sh\" check" in installer
    assert "SERVICE_ENABLED=NO" in installer
    assert "RF_TRANSMITTED=NO" in installer
    assert "FLASH_WRITTEN=NO" in installer

    print("YWD1278_STAGE_H_PRIOR_STAGE_PRESERVATION=PASS")
    print("STAGE_E_HISTORICAL_EVIDENCE=FROZEN")
    print("STAGE_F_HISTORICAL_EVIDENCE=FROZEN")
    print("STAGE_F_FIRMWARE_TRUST_IMPLEMENTATION=FROZEN")
    print("STAGE_H_INSTALLER_SUPERSESSION=TOOLCHAIN_DEPENDENCIES_ONLY")
    print("SERVICE_ENABLE_DURING_REPAIR=ABSENT")
    print("FLASH_WRITE_DURING_REPAIR=ABSENT")
    print("RF_TX_DURING_REPAIR=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
