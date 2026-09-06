#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Historical Stage-E/F qualification evidence remains immutable. Current
# product installer/deployer code may supersede those old implementations, but
# the historical qualification record and its pinned implementation blob IDs
# remain the authority for what Stage E/F actually qualified at the time.
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
}

HISTORICAL_STAGE_F_DEPLOY_BLOB = "94adb8ddd4dfebd90a1ea105203afc6a5049e828"
HISTORICAL_STAGE_F_HEAD = "3a976d6209752411b3a2823db6ffcc6ce341fd6a"


def blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def main() -> int:
    for path, expected in FROZEN.items():
        actual = blob(path)
        assert actual == expected, f"historical Stage-E/F evidence drift: {path}: {actual} != {expected}"

    stage_f = json.loads(
        (ROOT / "firmware/qualification/0b-product-firmware-trust-stage-f.json").read_text(encoding="utf-8")
    )
    assert stage_f["implementation"]["deploy_path"] == "installer/deploy-product-firmware.sh"
    assert stage_f["implementation"]["deploy_blob"] == HISTORICAL_STAGE_F_DEPLOY_BLOB
    assert stage_f["host_qualification"]["qualified_implementation_head"] == HISTORICAL_STAGE_F_HEAD
    assert stage_f["host_qualification"]["ci_conclusion"] == "success"
    assert stage_f["hardware_activity"]["rf"] is False
    assert stage_f["hardware_activity"]["flash"] is False

    # The current installer may evolve after Stage H, but the bare-metal
    # dependencies discovered by the Stage-H physical run must remain present.
    installer = (ROOT / "installer/install.sh").read_text(encoding="utf-8")
    assert "libnewlib-arm-none-eabi" in installer
    assert "libstdc++-arm-none-eabi-dev" in installer
    assert "libstdc++-arm-none-eabi-newlib" in installer
    assert "firmware-toolchain-check.sh\" check" in installer
    assert "SERVICE_ENABLED=NO" in installer
    assert "RF_TRANSMITTED=NO" in installer
    assert "FLASH_WRITTEN=NO" in installer

    # Current HAT-first deployer supersedes the old Stage-F shell blob under its
    # own current contracts; it must not rewrite the historical Stage-F record.
    current_deployer = blob("installer/deploy-product-firmware.sh")
    assert current_deployer != HISTORICAL_STAGE_F_DEPLOY_BLOB

    print("YWD1278_STAGE_H_PRIOR_STAGE_PRESERVATION=PASS")
    print("STAGE_E_HISTORICAL_EVIDENCE=FROZEN")
    print("STAGE_F_HISTORICAL_EVIDENCE=FROZEN")
    print("STAGE_F_QUALIFIED_DEPLOY_BLOB=PINNED_IN_HISTORICAL_RECORD")
    print("CURRENT_DEPLOYER_SUPERSESSION=HAT_FIRST_CONTRACT_GATED")
    print("STAGE_H_TOOLCHAIN_DEPENDENCIES=PRESERVED")
    print("SERVICE_ENABLE_DURING_UART_REPAIR=ABSENT")
    print("FLASH_WRITE_DURING_UART_REPAIR=ABSENT")
    print("RF_TX_DURING_UART_REPAIR=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
