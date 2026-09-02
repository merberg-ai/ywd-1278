#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.modem.rx_config import (  # noqa: E402
    RX_MODEM_IO_CONFIG,
    arm_rx_modem_io_request,
    set_rx_frequency_request,
)

TARGETS = ROOT / "firmware" / "targets.json"
ACTIVATE = ROOT / "firmware" / "activate-packet-live-rx.sh"
LIVE = ROOT / "tools" / "qualify_live_rx_owner.py"

data = json.loads(TARGETS.read_text(encoding="utf-8"))
t = data["targets"][0]

# The target has advanced through P13b, but this contract deliberately locks
# the complete P12a activation and physical evidence objects below unchanged.
assert t["status"] == "0b-p13b-known-packet-tx-qualified"
assert t["flash_enabled"] is False
assert t["option_bytes_permitted"] is False
assert t["qualification_write"]["phase"] == "0B-P3"
assert t["qualification_write"]["enabled"] is False
assert t["packet_qualification_write"]["phase"] == "0B-P11"
assert t["packet_qualification_write"]["enabled"] is False
assert t["packet_live_tx_qualification"]["status"] == "qualified"

q = t["packet_live_rx_activation"]
assert q == {
    "phase": "0B-P12a",
    "enabled": False,
    "requires_exact_stock_start": True,
    "requires_verified_stock_backup": True,
    "requires_automatic_stock_recovery_on_failure": True,
    "leave_packet_firmware_installed_on_success": True,
    "receive_frequency_hz": 144390000,
    "tx_command_permitted": False,
    "option_bytes_permitted": False,
}

p = t["packet_firmware_candidate"]
assert p["status"] == "deterministic-build-and-runtime-qualified"
assert p["artifact_size_bytes"] == 59812
assert p["artifact_sha256"] == "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310"
assert p["runtime_identity_verified"] is True
assert p["accepted_running_identity"] is True
assert p["expected_identity"] in t["accepted_running_identities"]
assert t["packet_runtime_qualification"]["phase"] == "0B-P11"
assert t["packet_runtime_qualification"]["status"] == "qualified"
assert t["packet_runtime_qualification"]["rf_transmitted"] is False

qr = t["packet_live_rx_qualification"]
assert qr == {
    "phase": "0B-P12a",
    "status": "qualified",
    "date": "2026-09-02",
    "artifact_size_bytes": 59812,
    "artifact_sha256": "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310",
    "programmed_readback_sha256": "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310",
    "packet_identity_verified": True,
    "main_flash_write_occurred": True,
    "receive_frequency_hz": 144390000,
    "live_rx_duration_seconds": 3,
    "packed_bytes_drained": 7210,
    "read_transactions": 1910,
    "status_checks": 7,
    "initial_samples": 20,
    "final_samples": 57682,
    "samples_advanced": 57662,
    "peak_fifo_available_bytes": 4,
    "fifo_dropped_bytes": 0,
    "rx_active_flags": "0x0D",
    "rx_idle_flags": "0x04",
    "rf_keyups_before": 0,
    "rf_keyups_after": 0,
    "rf_tx_generated_samples_before": 0,
    "rf_tx_generated_samples_after": 0,
    "rf_tx_active_after": False,
    "single_modem_owner": True,
    "modem_owner_transactions": 1926,
    "uart_released": True,
    "final_packet_restarted": True,
    "packet_firmware_left_installed": True,
    "rf_receive_configured": True,
    "tx_command_path_present": False,
    "rf_transmitted": False,
    "option_bytes_written": False,
}

# Frozen RX setup bytes are explicit and typed.
assert set_rx_frequency_request(144_390_000) == bytes.fromhex(
    "e0 0d 04 00 70 37 9b 08 70 37 9b 08 01"
)
assert RX_MODEM_IO_CONFIG == bytes.fromhex("80 02 00 00 00 78 01 00 00 32 32 32 32")
assert arm_rx_modem_io_request() == bytes.fromhex(
    "e0 10 02 80 02 00 00 00 78 01 00 00 32 32 32 32"
)
assert not hasattr(ModemOwner, "rf_tx_tones")
assert not hasattr(ModemOwner, "transact")

s = ACTIVATE.read_text(encoding="utf-8")
live = LIVE.read_text(encoding="utf-8")

# The one-purpose activation harness remains in-tree, but its manifest gate is
# closed after successful physical P12a proof.
assert 'QUALIFY-0B-P12A' in s
assert 'ACTIVATE-PACKET-RX-ONLY' in s
assert '[[ "$flash_enabled" == false ]]' in s
assert '[[ "$p3_enabled" == false && "$p11_enabled" == false ]]' in s
assert '[[ "$q_phase" == 0B-P12a && "$q_enabled" == true ]]' in s
assert 'Firmware does not match the exact P10/P11 qualified packet SHA256' in s
assert 'P12a must start from the exact protected stock identity' in s
assert 'Competing modem service is active:' in s
assert 'UART already has an owner before P12a' in s

# Main flash write gets exact artifact readback; failure gets complete stock recovery.
assert 'stm32flash -b 115200 -w "$FIRMWARE" -v "$DEVICE"' in s
assert 'PACKET_READBACK_SHA256=' in s
assert 'stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"' in s
assert 'EMERGENCY_STOCK_RESTORE_READBACK_SHA256=' in s
assert 'EMERGENCY_STOCK_RESTORE=PASS' in s
assert 'PACKET_WRITTEN == 1 && STOCK_RESTORED == 0' in s

# Success is intentionally different from P11: packet firmware remains installed,
# but it is reset cold after the RX lifecycle and the UART must be free.
assert 'Live receive-only owner/FIFO lifecycle' in s
assert 'Cold restart packet firmware for P12b' in s
assert 'PACKET_FIRMWARE_LEFT_INSTALLED=YES' in s
assert 'FINAL_PACKET_RESTARTED=YES' in s
assert 'MODEM_UART_RELEASED=YES' in s
assert 'RF_RECEIVE_CONFIGURED_DURING_TEST=YES' in s
assert 'TX_COMMAND_PATH=ABSENT' in s
assert 'RF_TRANSMITTED=NO' in s
assert 'OPTION_BYTES_WRITTEN=NO' in s

# Duration must be an ordinary fixed variable, not Bash's auto-incrementing SECONDS.
assert 'DURATION_SECONDS=3' in s
assert '--seconds) DURATION_SECONDS=' in s
assert not any(line.lstrip().startswith("SECONDS=") for line in s.splitlines())

# Live tool can only reach the serial device through ModemOwner typed methods.
assert 'posix_serial_transport_factory(args.device)' in live
assert 'ModemOwner(' in live
assert 'owner.set_rx_frequency' in live
assert 'owner.arm_rx_modem_io' in live
assert 'owner.rx_start' in live
assert 'owner.rx_read' in live
assert 'owner.rx_status' in live
assert 'owner.rx_stop' in live
assert 'owner.rf_status' in live
assert 'owner.rf_diagnostics' in live
assert '.transact(' not in live
assert 'owner.rf_tx' not in live
assert 'owner.rf_abort' not in live
assert 'RF_KEYUPS=' in live
assert 'RF_TX_ACTIVE=0' in live
assert 'FIFO_DROPPED_BYTES=' in live
assert 'FIRMWARE_SAMPLES_ADVANCED=YES' in live

for text in (s, live):
    for forbidden in ("0x1FFFF800", "0x1ffff800", "0x1FFFF7E0", "0x1ffff7e0", " -g "):
        assert forbidden not in text

print("PACKET_LIVE_RX_ACTIVATION_CONTRACT=PASS")
print("TARGET_ADVANCED_TO_P13B=PASS")
print("NORMAL_FLASH_GATE=CLOSED")
print("P3_WRITE_GATE=CLOSED")
print("P11_WRITE_GATE=CLOSED")
print("P12A_ACTIVATION_GATE=CLOSED_AFTER_PROOF")
print("EXACT_PACKET_SHA_GATE=PASS")
print("EXACT_STOCK_RECOVERY=PASS")
print("RX_SETUP_BYTES=PASS")
print("SINGLE_UART_OWNER=PASS")
print("P12A_PHYSICAL_EVIDENCE=PASS")
print("FIFO_DROPPED_BYTES=0")
print("RF_KEYUPS=0")
print("RF_TX_GENERATED_SAMPLES=0")
print("TX_COMMAND_PATH=ABSENT")
print("OPTION_BYTE_WRITE_PATH=ABSENT")
