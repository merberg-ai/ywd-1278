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
assert t["status"] == "0b-p11-packet-roundtrip-qualified"
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
assert t["firmware_identity"] in t["accepted_running_identities"]
assert any(x["sha256"] == "db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3" for x in t["revoked_artifacts"])

q = t["qualification_write"]
assert q == {
    "phase": "0B-P3",
    "enabled": False,
    "requires_exact_stock_start": True,
    "requires_verified_stock_backup": True,
    "requires_stock_restore_same_run": True,
}

rq = t["runtime_qualification"]
assert rq == {
    "phase": "0B-P3",
    "status": "qualified",
    "date": "2026-09-02",
    "artifact_size_bytes": 57316,
    "artifact_sha256": "b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8",
    "programmed_readback_sha256": "b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8",
    "ywd_identity_verified": True,
    "stock_restore_sha256": "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684",
    "stock_identity_verified": True,
    "main_flash_write_occurred": True,
    "rf_transmitted": False,
    "option_bytes_written": False,
}

# P11 advances the target status without altering the frozen P3 evidence.
assert t["packet_qualification_write"]["enabled"] is False
assert t["packet_runtime_qualification"]["phase"] == "0B-P11"
assert t["packet_runtime_qualification"]["status"] == "qualified"

s = SCRIPT.read_text(encoding="utf-8")
r = RESTORE.read_text(encoding="utf-8")

# The P3 qualification path remains in-tree for audit/recovery work, but its
# manifest gate is closed after the successful physical qualification.
assert '[[ "$flash_enabled" == false ]]' in s
assert '[[ "$q_phase" == 0B-P3 && "$q_enabled" == true ]]' in s
assert 'QUALIFY-0B-P3' in s
assert 'WRITE-YWD-THEN-RESTORE-STOCK' in s

# Exact corrected artifact and exact P2 stock backup were mandatory.
assert 'Firmware does not match the exact 0B-P1R1 qualified SHA256' in s
assert 'backup lacks two-pass qualification' in s
assert 'backup does not match target stock SHA256' in s
assert '0B-P3 must start from the exact stock identity' in s

# Both the YWD write and stock restore require readback verification.
assert 'stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"' in s
assert 'YWD_READBACK_SHA256=' in s
assert 'Programmed YWD-1278 bytes match the exact 0B-P1R1 artifact' in s
assert 'stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"' in s
assert 'STOCK_RESTORE_READBACK_SHA256=' in s
assert 'Complete restored stock flash matches the exact P2 SHA256' in s
assert 'FINAL_IDENTITY=' in s

# A failed qualification after YWD write must still have an automatic stock
# recovery path if this harness is deliberately re-armed in future.
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
print("QUALIFICATION_WRITE_GATE=CLOSED_AFTER_P3")
print("P1R1_ARTIFACT_HASH=PASS")
print("P3_PROGRAMMED_READBACK=PASS")
print("P3_YWD_IDENTITY=PASS")
print("P3_STOCK_RESTORE_READBACK=PASS")
print("P3_STOCK_IDENTITY=PASS")
print("P3_MAIN_FLASH_WRITE_RECORDED=YES")
print("P3_EVIDENCE_PRESERVED_AFTER_P11=PASS")
print("FAILED_P1_ARTIFACT=REVOKED")
print("AUTOMATIC_STOCK_RECOVERY_TOOL=PASS")
print("OPTION_BYTE_WRITE_PATH=ABSENT")
