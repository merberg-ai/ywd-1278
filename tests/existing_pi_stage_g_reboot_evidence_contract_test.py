#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-existing-pi-stage-g-reboot-target-pi.json"

INSTALLED_COMMIT = "5cb6e072c61d00376c1c46db7832912d71cace26"
QUALIFIER_SHA = "2e5bcefb8f988c2366dc4d58cdc021c634a6f929"
IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

FROZEN_REBOOT_IMPLEMENTATION = {
    "tools/qualify_stage_g_reboot_rx.sh": "70f53da49788a20dc7f9af35bf7256f14d0070b9",
    "tools/qualify_stage_g_reboot_live_rx.py": "5ee123c3cc262ce2566b99151c56f1d77d02d1c1",
    "firmware/qualification/0b-product-existing-pi-stage-g-target-pi.json": "a21c7de8c419ce9e923e439558380818f6bd5c7c",
}


def blob(path: str) -> str:
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    for path, expected in FROZEN_REBOOT_IMPLEMENTATION.items():
        actual = blob(path)
        assert actual == expected, f"frozen Stage-G reboot boundary drift: {path}: {actual} != {expected}"

    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["stage"] == "G"
    assert d["status"] == "target-pi-reboot-qualified"

    product = d["product_under_test"]
    assert product["installed_commit"] == INSTALLED_COMMIT
    assert product["hardware"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert product["os"] == "Debian GNU/Linux 13 (trixie)"
    assert product["uart"] == "/dev/ttyAMA0"
    assert product["frequency_hz"] == 145050000
    assert product["tx_enabled"] is False
    assert product["automatic_flash_enabled"] is False
    assert product["runtime_identity"] == IDENTITY

    harness = d["qualification_harness"]
    assert harness["checkout_sha"] == QUALIFIER_SHA
    assert harness["actual_reboot_required"] is True
    assert harness["fresh_mheard_advance_required"] is True

    reboot = d["reboot_proof"]
    assert reboot["boot_id_before"] == "74906ed4-3611-41d6-a194-b749088597c5"
    assert reboot["boot_id_after"] == "975c108c-2989-4904-8df3-d716649ae3a4"
    assert reboot["boot_id_before"] != reboot["boot_id_after"]
    assert reboot["boot_id_changed"] is True
    assert reboot["pre_reboot_main_pid"] == 143398
    assert reboot["auto_started_main_pid"] == 1771
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
    assert trust["flash_written"] is False
    assert trust["rf_transmitted"] is False

    restart = d["post_identity_restart"]
    assert restart["kiss_loopback_port_8001"] == "pass"
    assert restart["console_loopback_port_8010"] == "pass"
    assert restart["service_enabled"] is True
    assert restart["service_active"] is True
    assert restart["final_main_pid"] == 2660

    rx = d["fresh_post_reboot_rx"]
    assert rx["result"] == "pass"
    assert rx["frequency_hz"] == 145050000
    assert rx["kiss_frame_bytes"] == 36
    assert rx["ax25_source"] == "KJ6YWD-5"
    assert rx["kiss_data_received"] is True
    assert rx["telnet_mheard_fresh_advance"] is True
    assert rx["pty_mheard_fresh_advance"] is True
    assert rx["tx_command_sent"] is False
    assert rx["kiss_data_sent"] is False
    assert rx["modem_uart_opened_by_qualifier"] is False
    assert rx["rf_transmitted_by_qualifier"] is False

    claims = d["qualified_claims"]
    for key in (
        "actual_reboot_proven",
        "service_auto_start",
        "runtime_readiness_survived",
        "service_eligibility_survived",
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
    assert claims["flash_write"] is False
    assert d["stage_g_complete"] is True
    assert d["physical_tx_permitted"] is False

    print("YWD1278_STAGE_G_REBOOT_TARGET_PI_EVIDENCE=PASS")
    print(f"PRODUCT_INSTALLED_COMMIT={INSTALLED_COMMIT}")
    print(f"QUALIFIER_CHECKOUT_SHA={QUALIFIER_SHA}")
    print("BOOT_ID_CHANGED=YES")
    print("SERVICE_AUTO_START=PASS")
    print("RUNTIME_READINESS_AFTER_REBOOT=PASS")
    print("SERVICE_ELIGIBILITY_AFTER_REBOOT=PASS")
    print("KISS_TELNET_PTY_AUTO_RETURN=PASS")
    print("UART_RELEASE_AND_AX25R4_IDENTITY=PASS")
    print("FRESH_RX_145050=PASS")
    print("TELNET_PTY_MHEARD_FRESH_ADVANCE=PASS")
    print("PHYSICAL_TX=NO")
    print("FLASH_WRITE=NO")
    print("STAGE_G_COMPLETE=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
