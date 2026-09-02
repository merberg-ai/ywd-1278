#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "firmware" / "targets.json"
TOOL = ROOT / "tools" / "qualify_live_rx_kiss.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
text = TOOL.read_text(encoding="utf-8")

# Post-qualification target state advances to P12b, while all P12a physical
# evidence remains frozen as the prerequisite boundary used by the test tool.
assert target["status"] == "0b-p12b-live-rf-kiss-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_activation"]["enabled"] is False
assert target["packet_live_rx_qualification"]["phase"] == "0B-P12a"
assert target["packet_live_rx_qualification"]["status"] == "qualified"
assert target["packet_live_rx_qualification"]["receive_frequency_hz"] == 144390000
assert target["packet_live_rx_qualification"]["packed_bytes_drained"] == 7210
assert target["packet_live_rx_qualification"]["samples_advanced"] == 57662
assert target["packet_live_rx_qualification"]["fifo_dropped_bytes"] == 0
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
assert target["packet_live_rx_qualification"]["rf_keyups_before"] == 0
assert target["packet_live_rx_qualification"]["rf_keyups_after"] == 0
assert target["packet_live_rx_qualification"]["rf_tx_generated_samples_before"] == 0
assert target["packet_live_rx_qualification"]["rf_tx_generated_samples_after"] == 0
assert target["packet_live_rx_qualification"]["rf_transmitted"] is False

# P12b is now physical evidence at the corrected local packet-network frequency.
p12b = target["packet_live_rf_kiss_qualification"]
assert p12b["phase"] == "0B-P12b"
assert p12b["status"] == "qualified"
assert p12b["date"] == "2026-09-02"
assert p12b["receive_frequency_hz"] == 145050000
assert p12b["packet_identity_verified"] is True
assert p12b["kiss_listen_host"] == "127.0.0.1"
assert p12b["kiss_listen_port"] == 8001
assert p12b["qualification_wait_limit_seconds"] == 120
assert p12b["minimum_frames_required"] == 1
assert p12b["live_frames"] == 1
assert p12b["decoded_frames"] == 1
assert p12b["source"] == "KJ6YWD"
assert p12b["destination"] == "JIM"
assert p12b["digipeater_path"] == ["KRDG", "KBANN", "KJOHN", "KBULN", "WOODY"]
assert p12b["frame_type"] == "UI"
assert p12b["pid"] == "0xF0"
assert p12b["information_text"] == "test test"
assert p12b["frame_bytes"] == 60
assert p12b["frame_hex"] == (
    "94929a404040e096946cb2ae886096a4888e4040609684829c9c4060"
    "96949e909c40609684aa989c4060ae9e9e88b2406103f0746573742074657374"
)
assert p12b["packed_bytes"] == 27101
assert p12b["read_transactions"] == 2511
assert p12b["status_checks"] == 24
assert p12b["firmware_samples"] == 216815
assert p12b["fifo_dropped_bytes"] == 0
assert p12b["modem_owner_transactions"] == 2543
assert p12b["kiss_tx_rejected"] == 1
assert p12b["kiss_subscriber_drops"] == 0
assert p12b["rf_keyups_before"] == 0
assert p12b["rf_keyups_after"] == 0
assert p12b["rf_tx_generated_samples_before"] == 0
assert p12b["rf_tx_generated_samples_after"] == 0
assert p12b["single_modem_owner"] is True
assert p12b["uart_released"] is True
assert p12b["main_flash_write_occurred"] is False
assert p12b["gpio_accessed"] is False
assert p12b["tx_command_path_present"] is False
assert p12b["rf_transmitted"] is False
assert p12b["option_bytes_written"] is False
assert p12b["tx_command_permitted"] is False
assert p12b["option_bytes_permitted"] is False

# The frozen P12b qualification tool still records the exact pre-qualification
# gate it was physically run against. The post-evidence manifest intentionally
# no longer satisfies that staged-state gate, preventing accidental re-use as
# if P12b had not already been qualified.
assert 'target.get("status") != "0b-p12a-live-rx-qualified"' in text
assert 'P12A_HISTORICAL_RECEIVE_FREQUENCY_HZ = 144390000' in text
assert 'P12B_RECEIVE_FREQUENCY_HZ = 145050000' in text
assert 'packet_live_rx_qualification' in text
assert 'staging = target.get("packet_live_rf_kiss_qualification") or {}' in text
assert 'staging.get("phase") != "0B-P12b" or staging.get("status") != "staged"' in text
assert 'frequency_hz = int(target["packet_live_rf_kiss_qualification"]["receive_frequency_hz"])' in text
assert 'target["packet_live_rx_qualification"]["receive_frequency_hz"]' not in text
assert 'RXOnlyPacketRuntime(' in text
assert 'posix_serial_transport_factory(args.device)' in text
assert 'ModemOwner(' in text
assert 'frequency_hz=frequency_hz' in text
assert 'RXOnlyBackend(' in text
assert 'start_server_thread(backend, host=args.host, port=args.port)' in text
assert 'KISSStreamDecoder()' in text
assert 'parse_frame(message.frame, has_fcs=False)' in text
assert 'LIVE_KISS[' in text
assert 'YWD1278_0B_P12B_LIVE_RF_KISS=PASS' in text

# Listener is qualification-local only and inbound KISS DATA remains rejected.
assert 'args.host not in {"127.0.0.1", "localhost"}' in text
assert 'client.sendall(encode(b"P12B CLIENT TX MUST REMAIN DISCONNECTED"))' in text
assert 'backend.snapshot.tx_rejected != 1' in text
assert 'KISS_CLIENT_TX_PATH=REJECTED' in text

# RF diagnostics prove no TX activity occurred during the live receive test.
assert 'owner.rf_diagnostics' in text
assert 'diag_after.keyups != diag_before.keyups' in text
assert 'diag_after.generated_samples != diag_before.generated_samples' in text
assert 'RF_TRANSMITTED=NO' in text
assert 'TX_COMMAND_PATH=ABSENT' in text

# The qualification does not flash, reset, or expose a transmit command.
for forbidden in (
    "stm32flash",
    "hat_control.py",
    "bootloader-entry",
    "application-restart",
    "rf_tx_tones",
    "owner.rf_tx",
    "owner.rf_abort",
    "YWD_RF_TX_TONES",
    "TX_TONES",
    "0x1FFFF800",
    "0x1ffff800",
):
    assert forbidden not in text, forbidden

assert 'FLASH_WRITTEN=NO' in text
assert 'GPIO_ACCESSED=NO' in text
assert 'MODEM_UART_RELEASED=YES' in text
assert 'FIFO_DROPPED_BYTES=' in text
assert 'KISS_SUBSCRIBER_DROPS=' in text

print("LIVE_RX_KISS_CONTRACT=PASS")
print("P12A_PHYSICAL_PREREQUISITE=PASS")
print("P12A_144390_EVIDENCE_FROZEN=PASS")
print("P12B_145050_PHYSICAL_EVIDENCE=PASS")
print("P12B_LIVE_FRAME_LOCKED=PASS")
print("REAL_UART_SINGLE_OWNER=PASS")
print("LIVE_RX_RUNTIME=PASS")
print("LOOPBACK_KISS_ONLY=PASS")
print("KISS_CLIENT_TX_PATH=REJECTED")
print("RF_DIAGNOSTIC_TX_DELTA_GATE=PASS")
print("FLASH_PATH=ABSENT")
print("GPIO_PATH=ABSENT")
print("TX_COMMAND_PATH=ABSENT")
