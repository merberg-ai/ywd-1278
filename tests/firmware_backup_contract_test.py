#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "firmware" / "targets.json"
FLASH = ROOT / "firmware" / "flash.sh"
CONTROL = ROOT / "firmware" / "hat_control.py"

data = json.loads(TARGETS.read_text(encoding="utf-8"))
assert data["schema"] == 1
targets = data["targets"]
assert len(targets) == 1
t = targets[0]

assert t["id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert t["status"].startswith("0b-p2-read-only-qualified")
assert t["flash_enabled"] is False
assert t["option_bytes_permitted"] is False
assert t["flash_base"] == "0x08000000"
assert t["flash_size_bytes"] == 131072
assert t["geometry_status"] == "0b-p2-physically-qualified-two-pass-stock-backup"
assert t["expected_bootloader_version"] == "0x22"
assert t["expected_device_id"] == "0x0410"
assert t["stock_flash_sha256"] == "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"

hc = t["host_control"]
assert t["bootloader_entry"] == "pi-gpio20-21"
assert hc["boot0_gpio"] == 20
assert hc["reset_gpio"] == 21
assert hc["application_boot0_level"] == "low"
assert hc["application_reset_level"] == "high"
assert hc["application_release_pulses_reset"] is False
assert hc["bootloader_boot0_level"] == "high"
assert hc["reset_assert_level"] == "low"
assert hc["reset_release_level"] == "high"
assert hc["reset_pulse_seconds"] == 0.2
assert hc["bootloader_entry_pulses_reset"] is True
assert hc["application_restart_pulses_reset"] is True

flash = FLASH.read_text(encoding="utf-8")
control = CONTROL.read_text(encoding="utf-8")

# 0B-P2 backup must explicitly use target-aware GPIO entry/restart, two read
# passes, a byte comparison, and the known stock SHA gate.
assert 'bootloader-entry --targets "$TARGETS" --target "$TARGET_ID"' in flash
assert 'application-restart --targets "$TARGETS" --target "$TARGET_ID"' in flash
assert 'read-a.bin' in flash and 'read-b.bin' in flash
assert 'cmp -s "$read_a" "$read_b"' in flash
assert 'BACKUP_READ_PASSES=2' in flash
assert 'BACKUP_TWO_PASS_IDENTICAL=YES' in flash
assert 'STOCK_SHA256_MATCH=YES' in flash
assert 'OPTION_BYTES_READ=NO' in flash

# P2 remains qualified while P3 attempt 2 is armed for one exact P1R1 artifact.
assert t["qualification_write"]["enabled"] is True
assert t["qualification_write"]["phase"] == "0B-P3"
assert t["firmware_sha256"] == "b7ec163fc3a3cec395c0e3e3065f20c6dc6be186e32ccdcf9044c85ec681b9b8"
assert t["firmware_artifact"].endswith("MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed-hse8m.bin")
assert t["revoked_artifacts"]

# The main-flash backup range comes from the allowlisted target. There must be
# no option-byte/system-memory address in the backup tool.
for forbidden_address in ("0x1FFFF800", "0x1ffff800", "0x1FFFF7E0", "0x1ffff7e0"):
    assert forbidden_address not in flash

# A normal product write command may exist for future use, but it must stay
# behind the manifest flash_enabled gate and the target is still false.
gate = '[[ "$flash_enabled" == true ]] || die'
write = 'stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"'
assert gate in flash and write in flash
assert flash.index(gate) < flash.index(write)

# Control helper may pulse RESET only through the explicit qualified operations.
assert 'choices=["application-release", "auto-detect-release", "bootloader-entry", "application-restart"]' in control
assert 'HAT_BOOTLOADER_STATE_REQUESTED=YES' in control
assert 'HAT_APPLICATION_RESTARTED=YES' in control
assert 'MODEM_UART_OPENED=NO' in control
assert 'FLASH_WRITTEN=NO' in control
assert 'OPTION_BYTES_WRITTEN=NO' in control

print("FIRMWARE_BACKUP_CONTRACT=PASS")
print("GEOMETRY_QUALIFIED=131072")
print("STOCK_HASH_GATE=PASS")
print("TWO_PASS_READ_REQUIRED=PASS")
print("GPIO_BOOTLOADER_CONTROL=PASS")
print("P2_QUALIFICATION_PRESERVED_WHILE_P3_RETRY_ARMED=PASS")
print("NORMAL_FLASH_GATE_CLOSED=PASS")
print("OPTION_BYTE_ACCESS=ABSENT")
