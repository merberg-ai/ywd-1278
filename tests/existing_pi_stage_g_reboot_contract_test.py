#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_EVIDENCE = "firmware/qualification/0b-product-existing-pi-stage-g-target-pi.json"
TARGET_EVIDENCE_BLOB = "a21c7de8c419ce9e923e439558380818f6bd5c7c"


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def imports(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def main() -> int:
    assert blob(TARGET_EVIDENCE) == TARGET_EVIDENCE_BLOB, "qualified Stage-G RX evidence drift"

    prep = (ROOT / "tools/stage_g_reboot_prepare.sh").read_text(encoding="utf-8")
    qualify = (ROOT / "tools/qualify_stage_g_reboot_rx.sh").read_text(encoding="utf-8")
    live = (ROOT / "tools/qualify_stage_g_reboot_live_rx.py").read_text(encoding="utf-8")

    for required in (
        "/proc/sys/kernel/random/boot_id",
        "5cb6e072c61d00376c1c46db7832912d71cace26",
        "systemctl is-enabled",
        "systemctl is-active",
        "tx_enabled",
        "allow_automatic_flash",
        "145.050 MHz",
        "YWD1278_STAGE_G_REBOOT_PREPARE=PASS",
        "REBOOT_EXECUTED_BY_THIS_SCRIPT=NO",
    ):
        assert required in prep, f"reboot prepare missing token: {required}"

    for forbidden in (
        "systemctl reboot",
        "/sbin/reboot",
        "shutdown -r",
        "stm32flash",
        "WRITE-FIRMWARE-NOW",
        "deploy-product-firmware",
        "systemctl enable",
    ):
        assert forbidden not in prep, f"reboot prepare gained forbidden capability: {forbidden}"

    for required in (
        "/proc/sys/kernel/random/boot_id",
        "boot_after\" != \"$boot_before",
        "SERVICE_ELIGIBLE=YES",
        "service did not auto-start after reboot",
        "SERVICE_ACTIVE_BEFORE_QUALIFIER_MUTATION=YES",
        "systemctl stop",
        "UART ownership leaked after post-reboot stop",
        "hardware-detect.sh",
        "POST_REBOOT_EXACT_AX25R4_IDENTITY=PASS",
        "qualify_stage_g_reboot_live_rx.py",
        "YWD1278_STAGE_G_REBOOT_RX=PASS",
        "FRESH_TELNET_MHEARD_ADVANCE=PASS",
        "FRESH_PTY_MHEARD_ADVANCE=PASS",
        "TX_ENABLED=NO",
        "KISS_DATA_SENT=NO",
        "FLASH_WRITTEN=NO",
        "RF_TRANSMITTED_BY_QUALIFIER=NO",
    ):
        assert required in qualify, f"reboot qualifier missing token: {required}"

    assert qualify.index("SERVICE_ACTIVE_BEFORE_QUALIFIER_MUTATION=YES") < qualify.index("systemctl stop")
    assert qualify.index("boot_after\" != \"$boot_before") < qualify.index("systemctl stop")

    for forbidden in (
        "systemctl enable",
        "systemctl reboot",
        "stm32flash",
        "WRITE-FIRMWARE-NOW",
        "deploy-product-firmware",
        "TX_ACCEPT",
        "tx_enabled = true",
    ):
        assert forbidden not in qualify, f"reboot qualifier gained forbidden capability: {forbidden}"

    mods = imports("tools/qualify_stage_g_reboot_live_rx.py")
    for forbidden_prefix in ("serial", "subprocess", "ywd1278.modem", "ywd1278.tx"):
        assert not any(m.startswith(forbidden_prefix) for m in mods), f"post-reboot RX helper gained forbidden import: {forbidden_prefix}"

    for required in (
        "POST_REBOOT_MHEARD_BASELINE_CAPTURED=YES",
        "WAITING_FOR_FRESH_LIVE_PACKET_145050=YES",
        "base.recv_kiss_data",
        "advanced(before_telnet, after_telnet)",
        "advanced(before_pty, after_pty)",
        "TELNET_MHEARD_FRESH_ADVANCE=YES",
        "PTY_MHEARD_FRESH_ADVANCE=YES",
        "KISS_DATA_SENT=NO",
        "MODEM_UART_OPENED_BY_QUALIFIER=NO",
        "RF_TRANSMITTED_BY_QUALIFIER=NO",
    ):
        assert required in live, f"post-reboot live RX helper missing token: {required}"

    tree = ast.parse(live)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"send", "sendall", "sendto"}, "post-reboot helper gained socket send"

    print("YWD1278_STAGE_G_REBOOT_CONTRACT=PASS")
    print("FROZEN_STAGE_G_TARGET_RX_EVIDENCE=PASS")
    print("ACTUAL_KERNEL_BOOT_ID_CHANGE_REQUIRED=YES")
    print("SERVICE_AUTOSTART_PROVED_BEFORE_MUTATION=YES")
    print("POST_REBOOT_STAGE_F_ELIGIBILITY_REVALIDATION=REQUIRED")
    print("POST_REBOOT_UART_RELEASE_AND_EXACT_IDENTITY=REQUIRED")
    print("POST_REBOOT_FRESH_KISS_RX=REQUIRED")
    print("PERSISTENT_MHEARD_FRESH_ADVANCE=REQUIRED")
    print("REBOOT_SCRIPT_DOES_NOT_TRIGGER_REBOOT=YES")
    print("KISS_TX_FROM_REBOOT_QUALIFIER=ABSENT")
    print("FIRMWARE_WRITE_FROM_REBOOT_QUALIFIER=ABSENT")
    print("PHYSICAL_TX_FROM_REBOOT_QUALIFIER=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
