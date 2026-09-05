#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json"

INSTALLED_COMMIT = "2f5299e65add072fea6ee55a54dc421faf00c276"
QUALIFIER_SHA = "1026ba58813b19995cdcc526b9c362c7a2d21a94"
IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

FROZEN_BOUNDARY = {
    "tools/stage_h_reboot_prepare.sh": "f6148e8a1536e153dbe71e3ca0b5bf6524f35ee7",
    "tools/qualify_stage_h_reboot_rx.sh": "b2a69adeb33cee031cb073828e6003b9d05935ca",
    "tools/qualify_stage_g_reboot_live_rx.py": "5ee123c3cc262ce2566b99151c56f1d77d02d1c1",
    "firmware/qualification/0b-product-fresh-os-stage-h-preinstall-target-pi.json": "098e775070db0947c99a8ab29d33c16654a75a27",
    "firmware/qualification/0b-product-fresh-os-stage-h-resume-target-pi.json": "df68a00a78adda394c8c2482114a73aa6ce775c4",
    "firmware/qualification/0b-product-fresh-os-stage-h-stock-backup-target-pi.json": "d7ab16ded12ac66d8a9e8678fab4458b46316472",
    "firmware/qualification/0b-product-fresh-os-stage-h-firmware-build-success-target-pi.json": "95441f02881ec7b0932f2eacf2f63223de3451f2",
    "firmware/qualification/0b-product-fresh-os-stage-h-firmware-deploy-target-pi.json": "4878afab0c9a8c603abec392ad62ed77f2347036",
    "firmware/qualification/0b-product-fresh-os-stage-h-live-rx-target-pi.json": "88684af6c13cf071483f8372b660e66b820bc39a",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    for path, expected in FROZEN_BOUNDARY.items():
        actual = blob(path)
        assert actual == expected, f"frozen Stage-H boundary drift: {path}: {actual} != {expected}"

    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "H"
    assert d["status"] == "target-pi-fresh-os-qualified"

    product = d["product_under_test"]
    assert product["installed_commit"] == INSTALLED_COMMIT
    assert product["hardware"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert product["os"] == "Debian GNU/Linux 13 (trixie)"
    assert product["arch"] == "aarch64"
    assert product["uart"] == "/dev/ttyAMA0"
    assert product["frequency_hz"] == 145050000
    assert product["tx_enabled"] is False
    assert product["automatic_flash_enabled"] is False
    assert product["runtime_identity"] == IDENTITY

    harness = d["qualification_harness"]
    assert harness["checkout_sha"] == QUALIFIER_SHA
    assert harness["installed_product_commit"] == INSTALLED_COMMIT
    assert harness["actual_reboot_required"] is True
    assert harness["service_autostart_checked_before_qualifier_mutation"] is True
    assert harness["fresh_mheard_advance_required"] is True

    reboot = d["reboot_proof"]
    assert reboot["boot_id_before"] == "79055777-d228-4c3d-9b74-dc27cd322297"
    assert reboot["boot_id_after"] == "e39c73d0-797f-4105-b21f-701d866c54bf"
    assert reboot["boot_id_before"] != reboot["boot_id_after"]
    assert reboot["boot_id_changed"] is True
    assert reboot["pre_reboot_main_pid"] == 4089
    assert reboot["auto_started_main_pid"] == 1107
    assert reboot["service_enabled_after_reboot"] is True
    assert reboot["service_active_before_qualifier_mutation"] is True
    assert reboot["pty_auto_return"] == "pass"
    assert reboot["kiss_loopback_port_8001_auto_return"] == "pass"
    assert reboot["console_loopback_port_8010_auto_return"] == "pass"

    trust = d["post_reboot_trust_revalidation"]
    assert trust["runtime_readiness"] == "ready"
    assert trust["service_eligibility"] == "yes"
    assert trust["uart_release_after_stop"] == "pass"
    assert trust["exact_ax25r4_identity_after_stop"] == "pass"
    assert trust["detected_target"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
    assert trust["flash_written"] is False
    assert trust["option_bytes_written"] is False
    assert trust["rf_transmitted"] is False

    restart = d["post_identity_restart"]
    assert restart["kiss_loopback_port_8001"] == "pass"
    assert restart["console_loopback_port_8010"] == "pass"
    assert restart["service_enabled"] is True
    assert restart["service_active"] is True
    assert restart["final_main_pid"] == 1257

    rx = d["fresh_post_reboot_rx"]
    assert rx["result"] == "pass"
    assert rx["frequency_hz"] == 145050000
    assert rx["kiss_frame_bytes"] == 65
    assert rx["ax25_source"] == "KJ6YWD"
    assert rx["kiss_data_received"] is True
    assert rx["telnet_mheard_fresh_advance"] is True
    assert rx["pty_mheard_fresh_advance"] is True
    assert rx["tx_command_sent"] is False
    assert rx["kiss_data_sent"] is False
    assert rx["modem_uart_opened_by_qualifier"] is False
    assert rx["rf_transmitted_by_qualifier"] is False

    chain = d["fresh_os_chain"]
    for key in (
        "preexisting_ywd1278_state_at_preinstall",
    ):
        assert chain[key] is False, key
    for key in (
        "uart_repair_and_reboot_resume_qualified",
        "deterministic_ax25r4_build_qualified",
        "protected_stock_backup_before_write_qualified",
        "stock_to_ax25r4_main_flash_write_qualified",
        "independent_programmed_readback_qualified",
        "exact_runtime_identity_qualified",
        "guarded_service_activation_qualified",
        "systemd_stop_start_restart_sigterm_qualified",
        "initial_live_rx_145050_qualified",
        "final_reboot_autostart_qualified",
        "fresh_post_reboot_rx_145050_qualified",
    ):
        assert chain[key] is True, key

    claims = d["qualified_claims"]
    for key in (
        "fresh_raspberry_pi_os_from_zero",
        "installer_uart_repair_reboot_resume",
        "protected_stock_backup_before_firmware_write",
        "exact_ax25r4_written_read_back_identified",
        "service_enabled_only_after_preconditions",
        "actual_final_reboot_proven",
        "service_auto_start",
        "runtime_readiness_survived_final_reboot",
        "service_eligibility_survived_final_reboot",
        "kiss_telnet_pty_auto_return",
        "uart_release_after_post_reboot_stop",
        "exact_ax25r4_identity_after_reboot",
        "fresh_live_rx_145050",
        "fresh_telnet_mheard_advance",
        "fresh_pty_mheard_advance",
        "service_enabled_final",
        "service_active_final",
    ):
        assert claims[key] is True, key
    assert claims["physical_tx"] is False
    assert claims["flash_write_during_final_reboot_qualifier"] is False
    assert d["stage_h_complete"] is True
    assert d["physical_tx_permitted_by_stage_h"] is False

    print("YWD1278_STAGE_H_REBOOT_TARGET_PI_EVIDENCE=PASS")
    print(f"PRODUCT_INSTALLED_COMMIT={INSTALLED_COMMIT}")
    print(f"QUALIFIER_CHECKOUT_SHA={QUALIFIER_SHA}")
    print("FRESH_OS_FROM_ZERO=PASS")
    print("UART_REPAIR_REBOOT_RESUME=PASS")
    print("STOCK_BACKUP_AND_AX25R4_WRITE_READBACK=PASS")
    print("SERVICE_ACTIVATION_AND_INITIAL_RX=PASS")
    print("FINAL_BOOT_ID_CHANGED=YES")
    print("SERVICE_AUTO_START=PASS")
    print("RUNTIME_READINESS_AFTER_REBOOT=PASS")
    print("SERVICE_ELIGIBILITY_AFTER_REBOOT=PASS")
    print("KISS_TELNET_PTY_AUTO_RETURN=PASS")
    print("UART_RELEASE_AND_AX25R4_IDENTITY=PASS")
    print("FRESH_RX_145050=PASS")
    print("TELNET_PTY_MHEARD_FRESH_ADVANCE=PASS")
    print("PHYSICAL_TX=NO")
    print("STAGE_H_COMPLETE=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
