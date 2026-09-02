#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "firmware" / "qualification" / "0c-p2-rssi-live-stage.json"
ACTIVATE = ROOT / "firmware" / "activate-rssi-live.sh"
PROBE = ROOT / "tools" / "qualify_live_rssi.py"
TARGETS = ROOT / "firmware" / "targets.json"

stage = json.loads(STAGE.read_text(encoding="utf-8"))
activate = ACTIVATE.read_text(encoding="utf-8")
probe = PROBE.read_text(encoding="utf-8")
target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]

assert stage == {
    "schema": 1,
    "phase": "0C-P2",
    "stage": "live-rssi-activation",
    "status": "staged",
    "date": "2026-09-02",
    "target_id": "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021",
    "physical_base": {
        "status": "0b-p13b-known-packet-tx-qualified",
        "artifact": "firmware/out/0b-p10-ax25r3-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0-7ff74ed-hse8m.bin",
        "artifact_size_bytes": 59812,
        "artifact_sha256": "a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310",
        "identity": "MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed",
    },
    "candidate": {
        "profile_id": "0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse",
        "artifact": "firmware/out/0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse/MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1-7ff74ed-hse8m.bin",
        "artifact_size_bytes": 59892,
        "artifact_sha256": "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616",
        "identity": "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed",
        "reproducible_builds": True,
        "rssi_subcommand": 5,
        "carrier_threshold_selected": False,
    },
    "activation": {
        "device": "/dev/ttyAMA0",
        "frequency_hz": 145050000,
        "duration_seconds": 20.0,
        "rssi_poll_interval_seconds": 0.05,
        "requires_exact_physical_base": True,
        "requires_verified_stock_backup": True,
        "automatic_base_restore_on_failure": True,
        "fallback_stock_restore_on_base_restore_failure": True,
        "leave_candidate_installed_on_success": True,
        "confirmation_token": "QUALIFY-0C-P2-RSSI-RX-ONLY",
    },
    "safety": {
        "normal_product_flash_enabled": False,
        "qualification_write_only": True,
        "rx_configuration_permitted": True,
        "rssi_read_permitted": True,
        "tx_command_permitted": False,
        "kiss_tx_connected": False,
        "product_tx_enabled": False,
        "automatic_tx_retry": False,
        "option_bytes_permitted": False,
        "carrier_threshold_selected": False,
        "hysteresis_selected": False,
    },
}

# The exact physical boundary remains P13b until this new firmware is actually
# activated and observed on the HAT.
assert target["status"] == "0b-p13b-known-packet-tx-qualified"
assert target["packet_firmware_candidate"]["artifact_size_bytes"] == 59812
assert target["packet_firmware_candidate"]["artifact_sha256"] == stage["physical_base"]["artifact_sha256"]
assert target["packet_live_tx_qualification"]["status"] == "qualified"
assert target["packet_live_tx_qualification"]["external_decodes_observed"] == 3
assert stage["candidate"]["artifact_size_bytes"] - stage["physical_base"]["artifact_size_bytes"] == 80

# Activation is intentionally one-purpose. No operator-selected target, device,
# frequency, firmware, threshold, or timing knobs can redirect the physical run.
for forbidden_cli in (
    "--target)",
    "--device)",
    "--frequency",
    "--firmware",
    "--seconds)",
    "--poll-interval)",
    "--threshold",
    "--hysteresis",
):
    assert forbidden_cli not in activate, forbidden_cli
for required in (
    "--stock-backup-dir)",
    "--confirm)",
    "QUALIFY-0C-P2-RSSI-RX-ONLY",
    "BASE_PREFLIGHT_READBACK_SHA256",
    "CANDIDATE_READBACK_SHA256",
    "AX25R3_BASE_RESTORE=PASS",
    "FALLBACK_STOCK_RESTORE=PASS",
    "YWD1278_0C_P2_AX25R4_LIVE_RSSI_ACTIVATION=PASS",
    "CARRIER_THRESHOLD_SELECTED=NO",
    "HYSTERESIS_SELECTED=NO",
    "RF_TRANSMITTED=NO",
    "OPTION_BYTES_WRITTEN=NO",
):
    assert required in activate, required

# A write attempt is marked before stm32flash runs, so a partial/failed flash
# still triggers rollback rather than being mistaken for a no-write failure.
assert activate.index("CANDIDATE_WRITE_ATTEMPTED=1") < activate.index(
    'stm32flash -b 115200 -w "$CANDIDATE" -v "$DEVICE"'
)
assert 'restore_base || restore_stock || echo "P2_AUTOMATIC_RECOVERY=FAIL"' in activate
assert 'stm32flash -b 115200 -w "$BASE" -v "$DEVICE"' in activate
assert 'stm32flash -b 115200 -w "$STOCK_IMAGE" -v "$DEVICE"' in activate
assert 'readback_prefix_sha "$BASE_SIZE" p2-base-preflight' in activate
assert 'readback_prefix_sha "$CANDIDATE_SIZE" p2-candidate-readback' in activate

# The physical observation process uses only the base RX/control owner. It must
# drain raw capture while sampling RSSI and prove TX diagnostics do not change.
for required in (
    "ModemOwner(",
    "owner.rx_start",
    "owner.rx_read(200",
    "owner.rx_rssi",
    "owner.rx_status",
    "owner.rf_status",
    "owner.rf_diagnostics",
    "RSSI_SOURCE=ADF7021_REGISTER7_RAW_MAGNITUDE",
    "CARRIER_THRESHOLD_SELECTED=NO",
    "BUSY_CLEAR_DECISION=NO",
    "TX_COMMAND_PATH=ABSENT",
    "RF_TRANSMITTED=NO",
):
    assert required in probe, required
for forbidden in (
    "TXModemOwner",
    "TXBroker",
    "transmit_selector_burst",
    "rf_tx_tones_request",
    "YWD_RF_TX_TONES",
    "PersistentCSMA",
    "KISSServer",
    "stm32flash",
    "pinctrl",
    "raspi-gpio",
):
    assert forbidden not in probe, forbidden

# The activation wrapper itself may flash only the three explicit recovery/
# candidate images. It must not contain packet TX integrations or option-byte
# operations.
for forbidden in (
    "qualify_single_tx",
    "qualify_tx_sequence",
    "TXModemOwner",
    "TXBroker",
    "transmit_selector_burst",
    "YWD_RF_TX_TONES",
    "--option-bytes",
    "-o ",
):
    assert forbidden not in activate, forbidden

print("P2_RSSI_LIVE_ACTIVATION_CONTRACT=PASS")
print("PHYSICAL_BASE_STATUS=0b-p13b-known-packet-tx-qualified")
print("BASE_ARTIFACT_BYTES=59812")
print("BASE_ARTIFACT_SHA256=a069d9a9f1c3d5014984e5d73a5b57155ffa50f8908c9d80c5da221b8ea07310")
print("AX25R4_ARTIFACT_BYTES=59892")
print("AX25R4_ARTIFACT_SHA256=b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616")
print("ARTIFACT_DELTA_BYTES=80")
print("RX_FREQUENCY_HZ=145050000")
print("RSSI_POLL_INTERVAL_SECONDS=0.05")
print("RSSI_OBSERVATION_SECONDS=20.0")
print("AUTOMATIC_AX25R3_ROLLBACK=YES")
print("FALLBACK_EXACT_STOCK_RECOVERY=YES")
print("CARRIER_THRESHOLD_SELECTED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
