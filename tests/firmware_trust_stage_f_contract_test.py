#!/usr/bin/env python3
"""Architecture/safety contract for Stage-F product firmware trust/deployment."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_STAGE_E = {
    "src/ywd1278/install/readiness.py": "02f6115fb8ace1b1628b5c28f7560fe94ef663ac",
    "installer/install.sh": "58928db5368df0c0952cd8119617d754e8ed5d25",
    "installer/setup.sh": "305d71d06fd90f68cbb95f65ee94cb9fb12fe578",
    "installer/resume.sh": "7e2f0d7441b849d0165161208d2c52c9dbd3ae70",
    "systemd/ywd-1278.service": "ab7dc6aa6af8237d20e41a1357083f0321fd7062",
    "firmware/qualification/0b-product-installer-runtime-stage-e.json": "1d23b9dd0210ff65cc25bebc14040310da1d28e2",
}

FROZEN_FIRMWARE_FOUNDATION = {
    "firmware/flash.sh": "c4b618241442ba13439179870955e88eb288f19f",
    "firmware/targets.json": "846a293917c4ab35293e33dce2bf7b599a7cc122",
    "firmware/hat_control.py": "b83ffea0f93c30832435795e6da03d1e8292fe89",
    "firmware/probe_hat.py": "4210436ab950da4830ddea05020f642c40734c64",
    "firmware/build-packet-rssi-ywd1278.py": "5abf2db22e462be844207eb776fed9bae242dcb3",
    "firmware/tooling/packet-rssi-build-manifest.json": "c74f13fe0ae3ee786833f0f7a737111829027301",
    "installer/hardware-detect.sh": "9406e6c6f929244afadd2eca14ebeacbf364f2f4",
}

TARGET = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
AX25R4_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
STOCK_SHA = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)


def git_blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def assert_blobs(expected: dict[str, str], label: str) -> None:
    for path, blob in expected.items():
        actual = git_blob(path)
        assert actual == blob, f"{label} drift: {path}: expected {blob}, got {actual}"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    assert_blobs(FROZEN_STAGE_E, "frozen Stage E")
    assert_blobs(FROZEN_FIRMWARE_FOUNDATION, "frozen firmware foundation")

    profile = json.loads((ROOT / "firmware/product-ax25r4.json").read_text(encoding="utf-8"))
    trust_path = ROOT / "src/ywd1278/install/firmware_trust.py"
    trust = trust_path.read_text(encoding="utf-8")
    prepare = (ROOT / "firmware/prepare-product-ax25r4.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "installer/deploy-product-firmware.sh").read_text(encoding="utf-8")

    assert profile["schema"] == 1
    assert profile["product"] == "YWD-1278"
    assert profile["series"] == "AX25R4"
    assert profile["target_id"] == TARGET
    assert profile["expected_identity"] == IDENTITY
    assert profile["artifact_size_bytes"] == 59892
    assert profile["artifact_sha256"] == AX25R4_SHA
    assert profile["programmed_readback_bytes"] == 59892
    assert profile["programmed_readback_sha256"] == AX25R4_SHA
    assert profile["stock_flash_size_bytes"] == 131072
    assert profile["stock_flash_sha256"] == STOCK_SHA
    assert profile["expected_bootloader_version"] == "0x22"
    assert profile["expected_device_id"] == "0x0410"
    assert profile["flash_authorization_token"] == "FLASH-QUALIFIED-AX25R4"
    assert profile["final_write_confirmation"] == "WRITE-FIRMWARE-NOW"
    assert profile["service_eligibility_record"] == "/var/lib/ywd-1278/firmware-ready.json"
    assert profile["safety"] == {
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
    }

    modules = imported_modules(trust_path)
    for prefix in ("ywd1278.modem", "ywd1278.tx", "socket", "serial", "subprocess", "threading"):
        assert not any(module.startswith(prefix) for module in modules), (
            f"firmware trust boundary gained hardware/runtime dependency: {prefix}"
        )
    for token in ("/dev/ttyAMA0", "stm32flash", "systemctl", "os.open(", "openpty", "RX_START", "TX_ACCEPT"):
        assert token not in trust, f"zero-I/O trust module gained forbidden token: {token}"

    for token in (
        "build-packet-rssi-ywd1278.py",
        "YWD1278_PRODUCT_FIRMWARE_PREPARE=PASS",
        "HARDWARE_ACCESS=NO",
        "FLASH_WRITTEN=NO",
        "RF_TRANSMITTED=NO",
    ):
        assert token in prepare, f"product preparation missing token: {token}"
    assert "if [[ $EUID -eq 0 ]]" in prepare
    assert "stm32flash" not in prepare
    assert "hat_control" not in prepare

    required_deploy = (
        "FLASH-QUALIFIED-AX25R4",
        "Product runtime configuration must be READY",
        "systemctl disable --now ywd-1278.service",
        "UART is busy; Stage F refuses to stop an unknown owner automatically",
        'bash "$LEGACY_FLASH" backup',
        "YWD1278_STOCK_BACKUP_TRUST=PASS",
        "bootloader-entry",
        "STM32_BOOTLOADER_IDENTITY=PASS",
        "WRITE-FIRMWARE-NOW",
        'stm32flash -b 115200 -w "$FIRMWARE" -v "$device"',
        'stm32flash -b 115200 -r "$READBACK_TMP" -S "$flash_base:$readback_bytes" "$device"',
        "YWD1278_PROGRAMMED_READBACK=PASS",
        '[[ "$post_identity" == "$expected_identity" ]]',
        "write-eligibility",
        "check-eligibility",
        "PRODUCT_RUNTIME_IDENTITY_VERIFIED=YES",
        "STOCK_ROLLBACK_VERIFIED=YES",
        "OPTION_BYTES_WRITTEN=NO",
        "RF_TRANSMITTED=NO",
        "TX_ENABLED=NO",
        "SERVICE_ELIGIBLE=YES",
        "SERVICE_ENABLED=NO",
    )
    for token in required_deploy:
        assert token in deploy, f"product deployment missing safety/evidence token: {token}"

    for forbidden in (
        "systemctl enable ywd-1278.service",
        "systemctl enable --now ywd-1278.service",
        "systemctl start ywd-1278.service",
        "OPTION_BYTES_WRITTEN=YES",
        "tx_enabled = true",
        "TX_ACCEPT",
    ):
        assert forbidden not in deploy, f"Stage F deployment gained forbidden authority/token: {forbidden}"

    # Ordering is part of the safety contract: rollback proof precedes the
    # operator's final write confirmation; readback and exact identity precede
    # any service-eligibility evidence.
    assert deploy.index("YWD1278_STOCK_BACKUP_TRUST=PASS") < deploy.index("WRITE-FIRMWARE-NOW")
    assert deploy.index("YWD1278_PROGRAMMED_READBACK=PASS") < deploy.index("write-eligibility")
    assert deploy.index('[[ "$post_identity" == "$expected_identity" ]]') < deploy.index("write-eligibility")

    print("YWD1278_STAGE_F_FIRMWARE_TRUST_CONTRACT=PASS")
    print("FROZEN_STAGE_E_INSTALLER_RUNTIME=PASS")
    print("FROZEN_HISTORICAL_FLASH_TOOL=PASS")
    print("FROZEN_TARGET_HAT_CONTROL_PROBE=PASS")
    print("FROZEN_AX25R4_BUILD_LINEAGE=PASS")
    print("PRODUCT_PROFILE_AX25R4_SHA=PASS")
    print("PROTECTED_STOCK_BACKUP_REQUIRED=YES")
    print("EXPLICIT_FLASH_AUTHORIZATION_REQUIRED=YES")
    print("PROGRAMMED_READBACK_REQUIRED=YES")
    print("EXACT_RUNTIME_IDENTITY_REQUIRED=YES")
    print("OPTION_BYTES_PERMITTED=NO")
    print("TX_DURING_STAGE_F=DISABLED")
    print("SERVICE_ENABLE_AUTHORITY=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
