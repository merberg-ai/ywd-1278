#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "firmware" / "targets.json"
TOOL = ROOT / "tools" / "qualify_live_rx_kiss.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
text = TOOL.read_text(encoding="utf-8")

assert target["status"] == "0b-p12a-live-rx-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["packet_live_rx_activation"]["enabled"] is False
assert target["packet_live_rx_qualification"]["phase"] == "0B-P12a"
assert target["packet_live_rx_qualification"]["status"] == "qualified"
assert target["packet_live_rx_qualification"]["fifo_dropped_bytes"] == 0
assert target["packet_live_rx_qualification"]["packet_firmware_left_installed"] is True
assert target["packet_live_rx_qualification"]["rf_transmitted"] is False

# P12b must use the already-qualified packet firmware and assembled RX runtime.
assert 'target.get("status") != "0b-p12a-live-rx-qualified"' in text
assert 'packet_live_rx_qualification' in text
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

# RF diagnostics must prove no TX activity occurs during the live receive test.
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
print("REAL_UART_SINGLE_OWNER=PASS")
print("LIVE_RX_RUNTIME=PASS")
print("LOOPBACK_KISS_ONLY=PASS")
print("KISS_CLIENT_TX_PATH=REJECTED")
print("RF_DIAGNOSTIC_TX_DELTA_GATE=PASS")
print("FLASH_PATH=ABSENT")
print("GPIO_PATH=ABSENT")
print("TX_COMMAND_PATH=ABSENT")
