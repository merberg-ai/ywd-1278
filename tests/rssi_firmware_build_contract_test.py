#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402

MANIFEST = ROOT / "firmware" / "tooling" / "packet-rssi-build-manifest.json"
BUILDER = ROOT / "firmware" / "build-packet-rssi-ywd1278.py"
BRANDER = ROOT / "firmware" / "tooling" / "apply_packet_rssi_branding.py"
MATERIALIZER = ROOT / "firmware" / "tooling" / "materialize_vendored_engineering.py"
TARGETS = ROOT / "firmware" / "targets.json"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

m = json.loads(MANIFEST.read_text(encoding="utf-8"))
builder = BUILDER.read_text(encoding="utf-8")
brander = BRANDER.read_text(encoding="utf-8")
materializer = MATERIALIZER.read_text(encoding="utf-8")
targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

assert m["schema"] == 1
assert m["phase"] == "0C-P2"
assert m["profile_id"] == "0c-p2-rssi-ax25r4-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse"
assert m["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert m["upstream"]["commit"] == "7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5"
assert m["upstream"]["submodules"]["STM32F10X_Lib"] == "1debc23063f3942608e2bd62d04d5e1249c47fa3"
assert m["upstream"]["build_script_blob"] == "30257c0aea66695ed32877b8688daa835ee4f0e2"
assert m["build"]["stm32_hse_hz"] == 8_000_000
assert m["build"]["osc_override"] is False
assert m["rf"]["tcxo_hz"] == 14_745_600

eng = m["engineering"]
assert eng["source"] == "vendored"
assert eng["vendored_root"] == "firmware/vendor/ywd-mmdvm"
assert eng["baseline_qualified_commit"] == "d25180ad663d781b761c525d1e699e7b052d6214"
assert eng["commit"] == "69309644da839522102e393e66093378544869ea"
assert eng["baseline_qualification_blob"] == "42b4f22ba22050223fa9179b8d55045356e79a9d"
expected_order = [
    "firmware/stage4/apply_stage4.py",
    "firmware/ax25-classic1/apply_ax25_classic1.py",
    "firmware/ax25-classic1/apply_ax25_classic1_diag.py",
    "firmware/ax25-classic1/apply_ax25_classic1_continuity.py",
    "firmware/ax25-classic1/apply_ax25_classic1_reserve.py",
    "firmware/ax25-rx1/apply_ax25_rx1.py",
    "firmware/ax25-rx2/apply_ax25_rx2.py",
    "firmware/ax25-rx3/apply_ax25_rx3.py",
    "firmware/ax25-rx4/apply_ax25_rx4_rssi.py",
]
assert eng["transform_order"] == expected_order
assert len(eng["files"]) == 13
assert eng["files"]["firmware/ax25-classic1/apply_ax25_classic1_continuity.py"] == (
    "5796655bc91566b3c6c2627ea878a712720fbc7d"
)
assert eng["files"]["firmware/ax25-rx3/apply_ax25_rx3.py"] == (
    "bd49a33d62c025039e8d6f7a49cffb558eff1bda"
)
assert eng["files"]["firmware/ax25-rx4/apply_ax25_rx4_rssi.py"] == (
    "f69382dc0dbdb5c9d04bf2b04ea197d2840e5e03"
)

telemetry = m["telemetry"]
assert telemetry == {
    "namespace": "YWD_RX",
    "subcommand": 5,
    "source": "ADF7021 register-7 RSSI ADC readback",
    "wire_encoding": "uint16-le-raw-magnitude",
    "requires_active_ax25_rx": True,
    "blocked_during_tx": True,
    "carrier_threshold_selected": False,
}
branding = m["branding"]
assert branding["product_series"] == "AX25R4"
assert branding["firmware_version"] == "0.1.0-alpha1"
assert branding["legacy_version_token"] == "YWD-AX25R4-v0.2.3"
assert branding["legacy_info"] == "YWD-MMDVM-AX25R4"
assert branding["expected_info"] == "YWD-1278-AX25R4"
assert branding["expected_identity"] == (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
assert m["safety"] == {
    "hardware_access": False,
    "flash_enabled": False,
    "option_bytes_permitted": False,
    "rf_transmit_possible_during_build": False,
}

# Host protocol is additive: RX3 STATUS is unchanged; RSSI is 0x05.
assert protocol.RX_PROTOCOL_REVISION == 3
assert protocol.RX_RSSI == 0x05
assert protocol.rx_rssi_request() == bytes.fromhex("e0045905")
assert protocol.parse_rx_rssi(bytes.fromhex("e00659056d00")).raw_magnitude == 109
assert hasattr(ModemOwner, "rx_rssi")
assert not hasattr(ModemOwner, "transmit_selector_burst")
assert not hasattr(ModemOwner, "transact")

# Build pipeline is deterministic and obtains YWD engineering only from this repo.
for required in (
    "PINNED_UPSTREAM_SOURCE=PASS",
    "REPRODUCIBLE_BUILDS=PASS",
    "YWD1278_0C_P2_RSSI_FIRMWARE_BUILD=PASS",
    "ENGINEERING_SOURCE=VENDORED_IN_YWD1278",
    "ENGINEERING_EXTERNAL_REPO_REQUIRED=NO",
    "materialize_vendored_engineering.py",
    "arm-none-eabi-gcc",
):
    assert required in builder, required
for forbidden in (
    "--engineering-repo",
    "YWD1278_ENGINEERING_REPO",
    "mmdvm-lab/ywd-mmdvm",
    "/dev/ttyAMA0",
    "/dev/serial0",
    "stm32flash",
    "pinctrl",
    "raspi-gpio",
    "import RPi.GPIO",
    "gpiozero",
):
    assert forbidden not in builder, forbidden

for required in (
    "VENDORED_ENGINEERING_BLOBS=PASS",
    "ENGINEERING_EXTERNAL_REPO_REQUIRED=NO",
    "ENGINEERING_NETWORK_FETCH_REQUIRED=NO",
    "git_blob_sha1",
):
    assert required in materializer, required

# Branding locks the exact additive behavior and preserves the qualified R3 engine.
for required in (
    "AX25R4_RSSI_TELEMETRY_ANCHORS=PASS",
    "FROZEN_AX25R3_BEHAVIOR_ANCHORS=PASS",
    "YWD_RX_RSSI        = 0x05U",
    "const uint16_t rssi = io.readRSSI();",
    "!ax25AFSKRX.active() || m_tx || ax25AFSKTX.busy()",
    "reply[4U] = 3U",
    "CIO_FIFO_RESERVE = 256U",
    "0x000E006FU",
):
    assert required in brander, required

# The build manifest remains historical evidence that the firmware itself
# selected no carrier threshold. The current target has since advanced through
# physical AX25R4 correlation and the separate host-only 0C-P2 detector policy.
assert targets["status"] == "0c-p2-channel-busy-detector-qualified"
assert targets["packet_live_tx_qualification"]["external_decodes_observed"] == 3
assert targets["packet_rssi_qualification"]["status"] == "physically-qualified-correlation"
assert targets["channel_busy_qualification"]["status"] == "host-qualified"
assert targets["channel_busy_qualification"]["modem_integration"] is False
assert targets["channel_busy_qualification"]["csma_integration"] is False
for forbidden in (
    "RX_RSSI",
    "rx_rssi",
    "PersistentCSMA",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("RSSI_FIRMWARE_BUILD_CONTRACT=PASS")
print("PHASE=0C-P2")
print("BASELINE_AX25R3_COMMIT=d25180ad663d781b761c525d1e699e7b052d6214")
print("RSSI_ENGINEERING_COMMIT=69309644da839522102e393e66093378544869ea")
print("ENGINEERING_SOURCE=VENDORED_IN_YWD1278")
print("ENGINEERING_EXTERNAL_REPO_REQUIRED=NO")
print("ENGINEERING_FILES=13")
print("YWD_RX_RSSI_SUBCOMMAND=0x05")
print("RX_STATUS_REVISION=3")
print("FIRMWARE_CARRIER_THRESHOLD_SELECTED=NO")
print("P13B_PHYSICAL_BOUNDARY_RETAINED=PASS")
print("P2_CURRENT_TARGET_BOUNDARY=QUALIFIED")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("HARDWARE_ACCESS=NO")
print("RF_TRANSMITTED=NO")
