#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "firmware" / "targets.json"
SCRIPT = ROOT / "firmware" / "qualify-packet-roundtrip.sh"
RESTORE = ROOT / "firmware" / "restore-stock.sh"

data = json.loads(TARGETS.read_text(encoding="utf-8"))
t = data["targets"][0]

assert t["id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert t["flash_enabled"] is False
assert t["option_bytes_permitted"] is False
assert t["flash_size_bytes"] == 131072
assert t["stock_flash_sha256"] == "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"

# P3 remains frozen/closed. P11 gets a separate one-purpose gate.
assert t["qualification_write"]["phase"] == "0B-P3"
assert t["qualification_write"]["enabled"] is False
assert t["packet_qualification_write"] == {
    "phase": "0B-P11",
    "enabled": True,
    "requires_exact_stock_start": True,
    "requires_verified_stock_backup": True,
    "requires_stock_restore_same_run": True,
    "rf_configuration_permitted": False,
    "rx_start_permitted": False,
    "tx_command_permitted": False,
}

p = t["packet_firmware_candidate"]
assert p == {
    "phase": "0B-P10",
    "status": "deterministic-build-qualified-runtime-unqualified",
    "date": "2026-09-02",
    "artifact": "firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin",
    "artifact_size_bytes": 59812,
    "artifact_sha256": "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310",
    "expected_identity": "MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed",
    "packet_info": "YWD-1278-AX25R3",
    "engineering_commit": "d25180ad663d781b761c525d1e699e7b052d6214",
    "stm32_hse_hz": 8000000,
    "adf7021_tcxo_hz": 14745600,
    "osc_override": False,
    "reproducibility": "pass",
    "runtime_identity_verified": False,
    "accepted_running_identity": False,
}
assert p["expected_identity"] not in t["accepted_running_identities"]

s = SCRIPT.read_text(encoding="utf-8")
r = RESTORE.read_text(encoding="utf-8")

# Exact gate and explicit confirmations.
assert '[[ "$flash_enabled" == false ]]' in s
assert '[[ "$p3_enabled" == false ]]' in s
assert '[[ "$q_phase" == 0B-P11 && "$q_enabled" == true ]]' in s
assert 'QUALIFY-0B-P11' in s
assert 'WRITE-PACKET-YWD-THEN-RESTORE-STOCK' in s

# The exact build-qualified candidate and exact two-pass stock backup are mandatory.
assert 'Firmware does not match the exact 0B-P10 qualified packet SHA256' in s
assert 'Firmware size does not match the exact 0B-P10 packet artifact size' in s
assert 'backup lacks two-pass qualification' in s
assert 'backup does not match target stock SHA256' in s
assert '0B-P11 must start from the exact stock identity' in s

# Packet write and stock restore both require readback verification.
assert 'stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"' in s
assert 'PACKET_READBACK_SHA256=' in s
assert 'Programmed packet bytes match the exact 0B-P10 artifact' in s
assert 'stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"' in s
assert 'STOCK_RESTORE_READBACK_SHA256=' in s
assert 'Complete restored stock flash matches the exact P2 SHA256' in s
assert 'YWD1278_0B_P11_PACKET_ROUNDTRIP=PASS' in s

# Runtime proof is GET_VERSION only. No packet receive/transmit/config command is reachable.
assert 'probe_hat.py" --device "$DEVICE" --targets "$TARGETS" --no-application-release --json' in s
assert 'APPLICATION_COMMANDS_SENT=GET_VERSION_ONLY' in s
for forbidden in (
    "YWD_RX_START",
    "YWD_RX_READ",
    "YWD_RX_STOP",
    "YWD_RX_STATUS",
    "YWD_RF_TX_TONES",
    "TX_TONES",
    "MMDVM_YWD_RF",
    "MMDVM_YWD_RX",
):
    assert forbidden not in s

# Failure after packet write must automatically recover exact stock, including full readback.
assert 'emergency_stock_restore' in s
assert 'PACKET_WRITTEN == 1 && STOCK_RESTORED == 0' in s
assert 'EMERGENCY_STOCK_RESTORE_READBACK_SHA256=' in s
assert 'EMERGENCY_STOCK_RESTORE=PASS' in s

# GPIO bootloader entry/restart is the only hardware control path. Never write option bytes or jump.
assert 'bootloader-entry --targets "$TARGETS" --target "$TARGET_ID"' in s
assert 'application-restart --targets "$TARGETS" --target "$TARGET_ID"' in s
for text in (s, r):
    for forbidden in ("0x1FFFF800", "0x1ffff800", "0x1FFFF7E0", "0x1ffff7e0", " -g "):
        assert forbidden not in text

print("PACKET_FIRMWARE_ROUNDTRIP_CONTRACT=PASS")
print("NORMAL_FLASH_GATE=CLOSED")
print("P3_QUALIFICATION_GATE=CLOSED")
print("P11_PACKET_QUALIFICATION_GATE=ARMED")
print("P10_PACKET_SHA=PASS")
print("PACKET_RUNTIME_IDENTITY=UNQUALIFIED_UNTIL_PHYSICAL_P11")
print("APPLICATION_COMMAND_SET=GET_VERSION_ONLY")
print("RF_CONFIGURATION_PATH=ABSENT")
print("RX_START_PATH=ABSENT")
print("TX_COMMAND_PATH=ABSENT")
print("AUTOMATIC_FULL_STOCK_RECOVERY=PASS")
print("OPTION_BYTE_WRITE_PATH=ABSENT")
