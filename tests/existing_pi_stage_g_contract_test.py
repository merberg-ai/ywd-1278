#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_STAGE_F = {
    "firmware/product-ax25r4.json": "b7263fbe7bde1ad547207b7cc0e4f22220b38f72",
    "firmware/prepare-product-ax25r4.sh": "35abcbe4fed888dcd4f8e422e2954fc13e8f1ded",
    "installer/deploy-product-firmware.sh": "94adb8ddd4dfebd90a1ea105203afc6a5049e828",
    "src/ywd1278/install/firmware_trust.py": "5f119de52a9363adcb10eab8e007a2cee8cab158",
    "tests/firmware_trust_stage_f_test.py": "e6a97a46f7c6aae9390ebfb638634f92c1a8d1bb",
    "tests/firmware_trust_stage_f_contract_test.py": "6325ed29a828bd857d894a1d29e2cb87d25d04f2",
    "tests/firmware_trust_stage_f_qualification_contract_test.py": "436e3d5ac33f316d8194a9165e9d136b69659be5",
    "firmware/qualification/0b-product-firmware-trust-stage-f.json": "702598db66d7ab92c384850c6dfed973e697fe5e",
    "docs/qualifications/fresh-install-stage-f-firmware-trust-host-qualified-2026-09-04.md": "9f244846ca28dcb8afd6db9521ddad753c5ccd98",
    ".github/workflows/fresh-install-stage-f-firmware-trust-ci.yml": "d500121c643a3987ae91736c0a58b66b93b8e606",
}

FROZEN_DEPLOYED_RUNTIME = {
    "systemd/ywd-1278.service": "ab7dc6aa6af8237d20e41a1357083f0321fd7062",
    "installer/install.sh": "58928db5368df0c0952cd8119617d754e8ed5d25",
    "installer/hardware-detect.sh": "9406e6c6f929244afadd2eca14ebeacbf364f2f4",
    "src/ywd1278/install/readiness.py": "02f6115fb8ace1b1628b5c28f7560fe94ef663ac",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def imports(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def main() -> int:
    for label, files in (("Stage F", FROZEN_STAGE_F), ("deployed runtime", FROZEN_DEPLOYED_RUNTIME)):
        for path, expected in files.items():
            actual = blob(path)
            assert actual == expected, f"frozen {label} drift: {path}: expected {expected}, got {actual}"

    enable = (ROOT / "installer/enable-product-service.sh").read_text(encoding="utf-8")
    qualify_sh = (ROOT / "tools/qualify_stage_g_systemd_rx.sh").read_text(encoding="utf-8")
    live = (ROOT / "tools/qualify_stage_g_live_rx.py").read_text(encoding="utf-8")

    for required in (
        "check-eligibility",
        "SERVICE_ELIGIBLE=YES",
        "tx_enabled",
        "allow_automatic_flash",
        "145.050 MHz",
        "hardware-detect.sh",
        "detected_identity",
        "expected_identity",
        "systemctl enable --now ywd-1278.service",
        "TX_ENABLED=NO",
        "AUTOMATIC_FLASH=NO",
        "FLASH_WRITTEN=NO",
        "RF_TRANSMITTED=NO",
    ):
        assert required in enable, f"service activation gate missing token: {required}"

    enable_action = enable.index("systemctl enable --now ywd-1278.service")
    assert enable.index("check-eligibility") < enable_action
    assert enable.index("detected_identity") < enable_action
    assert enable.index("tx_enabled") < enable_action

    for forbidden in (
        "stm32flash",
        "WRITE-FIRMWARE-NOW",
        "bootloader-entry",
        "application-restart",
        "tx_enabled = true",
        "TX_ACCEPT",
        "KISS DATA TX",
    ):
        assert forbidden not in enable, f"Stage G service activation gained forbidden capability: {forbidden}"

    for required in (
        "systemctl stop",
        "systemctl start",
        "systemctl restart",
        "SIGTERM_CLEANUP=PASS",
        "UART_RELEASE=PASS",
        "qualify_stage_g_live_rx.py",
        "TX_ENABLED=NO",
        "KISS_DATA_SENT=NO",
        "FLASH_WRITTEN=NO",
        "REBOOT_QUALIFICATION=PENDING",
    ):
        assert required in qualify_sh, f"Stage G systemd qualifier missing token: {required}"

    for forbidden in (
        "systemctl enable",
        "stm32flash",
        "deploy-product-firmware",
        "WRITE-FIRMWARE-NOW",
        "bootloader-entry",
        "TX_ACCEPT",
    ):
        assert forbidden not in qualify_sh, f"RX-only qualifier gained forbidden authority: {forbidden}"

    mods = imports("tools/qualify_stage_g_live_rx.py")
    for forbidden_prefix in ("serial", "subprocess", "ywd1278.modem", "ywd1278.tx"):
        assert not any(m.startswith(forbidden_prefix) for m in mods), f"live RX helper gained forbidden import: {forbidden_prefix}"

    tree = ast.parse(live)
    recv_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "recv_kiss_data")
    for node in ast.walk(recv_fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"send", "sendall", "sendto"}, "KISS receive function gained a send call"

    assert "WAITING_FOR_LIVE_PACKET_145050=YES" in live
    assert "KISS_DATA_SENT=NO" in live
    assert "MODEM_UART_OPENED_BY_QUALIFIER=NO" in live
    assert "RF_TRANSMITTED_BY_QUALIFIER=NO" in live

    print("YWD1278_STAGE_G_EXISTING_PI_CONTRACT=PASS")
    print("FROZEN_STAGE_F_FIRMWARE_TRUST=PASS")
    print("FROZEN_DEPLOYED_RUNTIME=PASS")
    print("SERVICE_ENABLE_REQUIRES_STAGE_F_ELIGIBILITY=YES")
    print("SERVICE_ENABLE_REQUIRES_EXACT_AX25R4_IDENTITY=YES")
    print("SERVICE_ENABLE_REQUIRES_TX_DISABLED=YES")
    print("SYSTEMD_STOP_START_RESTART_SIGTERM=STAGED")
    print("LIVE_RX_145050=STAGED")
    print("KISS_RX_TELNET_MHEARD_PTY_MHEARD=STAGED")
    print("KISS_TX_FROM_QUALIFIER=ABSENT")
    print("FIRMWARE_WRITE_FROM_STAGE_G=ABSENT")
    print("REBOOT_QUALIFICATION=SEPARATE_PENDING_GATE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
