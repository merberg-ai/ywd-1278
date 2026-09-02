#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "firmware" / "targets.json"
SCRIPT = ROOT / "firmware" / "qualify-roundtrip.sh"
RESTORE = ROOT / "firmware" / "restore-stock.sh"

data = json.loads(TARGETS.read_text(encoding="utf-8"))
t = data["targets"][0]

assert t["id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert t["status"] == "0b-p2-read-only-qualified-p3-attempt2-armed"
assert t["flash_enabled"] is False
assert t["option_bytes_permitted"] is False
assert t["geometry_status"] == "0b-p2-physically-qualified-two-pass-stock-backup"
assert t["flash_size_bytes"] == 131072
assert t["stock_flash_sha256"] == "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
assert t["stm32_hse_hz"] == 8000000
assert t["tcxo_mhz"] == 14.7456
assert t["firmware_sha256"] == "b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8"
assert t["firmware_identity"] == "MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
assert t["firmware_artifact"] == "firmware/out/0b-p1r1-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed-hse8m.bin"
assert any(x["sha256"] == "db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3" for x in t["revoked_artifacts"])

q = t["qualification_write"]
assert q == {
    "phase": "0B-P3",
    "enabled": True,
    "requires_exact_stock_start": True,
    "requires_verified_stock_backup": True,
    "requires_stock_restore_same_run": True,
}

s = SCRIPT.read_text(encoding="utf-8")
r = RESTORE.read_text(encoding="utf-8")

# The qualification path must remain distinct from normal product flashing.
assert '[[ "$flash_enabled" == false ]]' in s
assert '[[ "$q_phase" == 0B-P3 && "$q_enabled" == true ]]' in s
assert 'QUALIFY-0B-P3' in s
assert 'WRITE-YWD-THEN-RESTORE-STOCK' in s

# Exact corrected artifact and exact P2 stock backup are mandatory.
assert 'Firmware does not match the exact 0B-P1 qualified SHA256' in s
assert 'backup lacks two-pass qualification' in s
assert 'backup does not match target stock SHA256' in s
assert '0B-P3 must start from the exact stock identity' in s

# Both the YWD write and stock restore require readback verification.
assert 'stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"' in s
assert 'YWD_READBACK_SHA256=' in s
assert 'Programmed YWD-1278 bytes match the exact 0B-P1 artifact' in s
assert 'stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"' in s
assert 'STOCK_RESTORE_READBACK_SHA256=' in s
assert 'Complete restored stock flash matches the exact P2 SHA256' in s
assert 'FINAL_IDENTITY=' in s

# A failed qualification after YWD write must attempt stock recovery.
assert 'emergency_stock_restore' in s
assert 'EMERGENCY_STOCK_RESTORE=PASS' in s
assert 'YWD_WRITTEN == 1 && STOCK_RESTORED == 0' in s

# The standalone recovery tool must itself work through the qualified GPIO path
# and verify a complete main-flash readback. No physical BOOT/RST interaction.
assert 'bootloader-entry --targets "$TARGETS" --target "$target_id"' in r
assert 'application-restart --targets "$TARGETS" --target "$target_id"' in r
assert 'STOCK_RESTORE_READBACK_SHA256=' in r
assert 'Restored main flash differs from exact stock SHA256' in r
assert 'Post-restore exact identity verification' in r
assert 'Hold BOOT' not in r
assert 'BOOTLOADER-READY' not in r

# GPIO bootloader entry/restart is the only control method and no option-byte
# memory addresses or jump/go command are permitted in these write tools.
assert 'bootloader-entry --targets "$TARGETS" --target "$TARGET_ID"' in s
assert 'application-restart --targets "$TARGETS" --target "$TARGET_ID"' in s
for text in (s, r):
    for forbidden in ("0x1FFFF800", "0x1ffff800", "0x1FFFF7E0", "0x1ffff7e0", " -g "):
        assert forbidden not in text

print("FIRMWARE_ROUNDTRIP_CONTRACT=PASS")
print("NORMAL_FLASH_GATE_CLOSED=PASS")
print("QUALIFICATION_WRITE_GATE=ARMED_FOR_P1R1")
print("P1R1_ARTIFACT_HASH=PASS")
print("FAILED_P1_ARTIFACT=REVOKED")
print("VERIFIED_STOCK_BACKUP_REQUIRED=PASS")
print("YWD_READBACK_REQUIRED=PASS")
print("STOCK_READBACK_REQUIRED=PASS")
print("EMERGENCY_STOCK_RECOVERY=REQUIRED")
print("AUTOMATIC_STOCK_RECOVERY_TOOL=PASS")
print("OPTION_BYTE_WRITE_PATH=ABSENT")
