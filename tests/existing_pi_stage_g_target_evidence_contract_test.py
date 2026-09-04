#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-existing-pi-stage-g-target-pi.json"

TESTED_SHA = "5cb6e072c61d00376c1c46db7832912d71cace26"
ARTIFACT_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
STOCK_SHA = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

FROZEN_STAGE_G_IMPLEMENTATION = {
    "installer/enable-product-service.sh": "fde63d07904d45046fd3ff372126f526b74f087b",
    "tools/qualify_stage_g_live_rx.py": "cbe7d7c30b3d666ca1949bc3558256bf603f5fd6",
    "tools/qualify_stage_g_systemd_rx.sh": "614a34eca52e329cfef11d6de2cc8ffb4593880b",
    "tests/existing_pi_stage_g_test.py": "28a0c47a60a1991f1adcdb68962471bd4e7ede02",
    "tests/existing_pi_stage_g_contract_test.py": "bf36679c47ec7653b7e7b3a1d0723344c7114e86",
    "firmware/qualification/0b-product-existing-pi-stage-g.json": "8bcdf42e7010ac66d796b4e855f14710f2acd3b9",
    "docs/qualifications/fresh-install-stage-g-existing-pi-staged-2026-09-04.md": "9b70c39a8200983b9e83d209ac6b6e29bbd2e153",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    for path, expected in FROZEN_STAGE_G_IMPLEMENTATION.items():
        actual = blob(path)
        assert actual == expected, f"frozen Stage-G implementation drift: {path}: {actual} != {expected}"

    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "G"
    assert d["status"] == "target-pi-rx-qualified-reboot-pending"
    assert d["host_staged_checkpoint"] == {
        "branch": "checkpoint/product-existing-pi-stage-g-host-staged",
        "sha": TESTED_SHA,
    }

    tested = d["tested_source"]
    assert tested["sha"] == TESTED_SHA
    assert tested["checkout_exact"] is True
    assert tested["working_tree_clean"] is True
    assert tested["child_test_exit_code"] == 0
    assert tested["putty_session_remained_open"] is True

    target = d["target"]
    assert target["host"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert target["os"] == "Debian GNU/Linux 13 (trixie)"
    assert target["uart"] == "/dev/ttyAMA0"
    assert target["runtime_identity"] == IDENTITY

    install = d["installed_appliance"]
    assert install["installer"] == "pass"
    assert install["installed_commit"] == TESTED_SHA
    assert install["station"] == "KJ6YWD-10"
    assert install["frequency_hz"] == 145050000
    assert install["kiss"] == "127.0.0.1:8001"
    assert install["telnet_console"] == "127.0.0.1:8010"
    assert install["pty"] == "/run/ywd-1278/tnc"
    assert install["runtime_readiness"] == "ready"
    assert install["uart_runtime_ready"] is True
    assert install["reboot_required_by_installer"] is False
    assert install["tx_enabled"] is False
    assert install["automatic_flash_enabled"] is False
    assert install["service_enabled_after_installer"] is False
    assert install["rf_transmitted_by_installer"] is False
    assert install["flash_written_by_installer"] is False

    fw = d["product_firmware"]
    assert fw["artifact_size_bytes"] == 59892
    assert fw["artifact_sha256"] == ARTIFACT_SHA
    assert fw["artifact_reproducible_builds"] == "pass"
    assert fw["hardware_access_during_prepare"] is False

    stage_f = d["stage_f_physical_trust"]
    assert stage_f["status"] == "pass"
    assert stage_f["existing_exact_ax25r4_verified_without_rewrite"] is True
    assert stage_f["stock_backup_sha256"] == STOCK_SHA
    assert stage_f["stock_backup_read_passes"] == 2
    assert stage_f["bootloader_version"] == "0x22"
    assert stage_f["device_id"] == "0x0410"
    assert stage_f["programmed_readback_sha256"] == ARTIFACT_SHA
    assert stage_f["programmed_readback"] == "pass"
    assert stage_f["runtime_identity_after_readback"] == "pass"
    assert stage_f["service_eligibility"] == "yes"
    assert stage_f["option_bytes_written"] is False
    assert stage_f["rf_transmitted"] is False
    assert stage_f["tx_enabled"] is False
    assert stage_f["flash_written"] is False
    assert stage_f["service_enabled"] is False

    activation = d["stage_g_service_activation"]
    assert activation["status"] == "pass"
    assert activation["installed_commit_verified"] is True
    assert activation["stage_f_eligibility_revalidated"] is True
    assert activation["live_exact_ax25r4_identity_rechecked"] is True
    assert activation["service_enabled"] is True
    assert activation["service_active"] is True
    assert activation["tx_enabled"] is False
    assert activation["automatic_flash_enabled"] is False
    assert activation["flash_written"] is False
    assert activation["rf_transmitted"] is False

    life = d["stage_g_lifecycle"]
    for key in (
        "systemd_stop",
        "sigterm_cleanup",
        "pty_cleanup",
        "uart_release",
        "systemd_start",
        "systemd_restart",
        "kiss_loopback_port_8001",
        "console_loopback_port_8010",
    ):
        assert life[key] == "pass", key
    assert life["stopped_main_pid"] == 143317
    assert life["start_main_pid"] == 143366
    assert life["restart_main_pid"] == 143398
    assert life["start_main_pid"] != life["restart_main_pid"]

    rx = d["stage_g_live_rx"]
    assert rx["frequency_hz"] == 145050000
    assert rx["console_health"] == "pass"
    assert rx["kiss_frame_bytes"] == 69
    assert rx["ax25_source"] == "KJ6YWD"
    assert rx["kiss_data_received"] is True
    assert rx["telnet_mheard_source_match"] is True
    assert rx["pty_mheard_source_match"] is True
    assert rx["tx_command_sent"] is False
    assert rx["kiss_data_sent"] is False
    assert rx["modem_uart_opened_by_qualifier"] is False
    assert rx["rf_transmitted_by_qualifier"] is False
    assert rx["result"] == "pass"

    claims = d["qualified_claims"]
    for key in (
        "existing_pi_installed_appliance_rx_rehearsal",
        "physical_firmware_trust",
        "service_activation_gate",
        "systemd_stop_start_restart_sigterm",
        "uart_release_after_stop",
        "live_rx_145050_to_kiss",
        "telnet_mheard",
        "pty_mheard",
    ):
        assert claims[key] is True, key
    assert claims["physical_tx"] is False
    assert claims["reboot_survival"] is False
    assert d["reboot_qualification_complete"] is False
    assert d["physical_tx_permitted"] is False

    print("YWD1278_STAGE_G_TARGET_PI_RX_EVIDENCE=PASS")
    print(f"TESTED_SOURCE_SHA={TESTED_SHA}")
    print("TARGET=RASPBERRY_PI_5_DEBIAN_13")
    print("INSTALLER_RUNTIME_READY=PASS")
    print("EXACT_AX25R4_REWRITE_REQUIRED=NO")
    print("STOCK_ROLLBACK_VERIFIED=PASS")
    print("PROGRAMMED_READBACK=PASS")
    print("SERVICE_ELIGIBILITY_AND_ACTIVATION=PASS")
    print("SYSTEMD_STOP_START_RESTART_SIGTERM=PASS")
    print("UART_AND_PTY_CLEANUP=PASS")
    print("LIVE_RX_145050_KISS=PASS")
    print("TELNET_AND_PTY_MHEARD=PASS")
    print("TX_ENABLED=NO")
    print("FLASH_WRITTEN=NO")
    print("RF_TRANSMITTED=NO")
    print("REBOOT_QUALIFICATION=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
