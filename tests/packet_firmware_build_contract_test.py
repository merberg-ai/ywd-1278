#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/tooling/packet-build-manifest.json"
BUILDER = ROOT / "firmware/build-packet-ywd1278.sh"
BRANDER = ROOT / "firmware/tooling/apply_packet_branding.py"

m = json.loads(MANIFEST.read_text(encoding="utf-8"))
builder = BUILDER.read_text(encoding="utf-8")
brander = BRANDER.read_text(encoding="utf-8")

assert m["schema"] == 1
assert m["phase"] == "0B-P10"
assert m["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
assert m["upstream"]["commit"] == "7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5"
assert m["upstream"]["submodules"]["STM32F10X_Lib"] == "1debc23063f3942608e2bd62d04d5e1249c47fa3"
assert m["build"]["stm32_hse_hz"] == 8_000_000
assert m["build"]["osc_override"] is False
assert m["rf"]["tcxo_hz"] == 14_745_600

eng = m["engineering"]
assert eng["repository"] == "merberg-ai/ywd-mmdvm"
assert eng["commit"] == "d25180ad663d781b761c525d1e699e7b052d6214"
assert eng["qualification_blob"] == "42b4f22ba22050223fa9179b8d55045356e79a9d"

expected_order = [
    "firmware/stage4/apply_stage4.py",
    "firmware/ax25-classic1/apply_ax25_classic1.py",
    "firmware/ax25-classic1/apply_ax25_classic1_diag.py",
    "firmware/ax25-classic1/apply_ax25_classic1_continuity.py",
    "firmware/ax25-classic1/apply_ax25_classic1_reserve.py",
    "firmware/ax25-rx1/apply_ax25_rx1.py",
    "firmware/ax25-rx2/apply_ax25_rx2.py",
    "firmware/ax25-rx3/apply_ax25_rx3.py",
]
assert eng["transform_order"] == expected_order
assert len(eng["files"]) == 12

expected_blobs = {
    "firmware/stage4/apply_stage4.py": "2fa3a3ca4b8470a90de58534cbe20646ea390c9a",
    "firmware/ax25-classic1/AX25AFSKTX.cpp": "95cbab582aa359854a58e3d7b456ae4ada0dfddf",
    "firmware/ax25-classic1/AX25AFSKTX.h": "ca187f153c2139e580c31b5cf635d1393cef5769",
    "firmware/ax25-classic1/apply_ax25_classic1.py": "91eccb3a196f731690e3e275041bbb1b73b18ed1",
    "firmware/ax25-classic1/apply_ax25_classic1_diag.py": "ca885602a4359991bdfa7f1a976d47e0ae3be3e7",
    "firmware/ax25-classic1/apply_ax25_classic1_continuity.py": "5796655bc91566b3c6c2627ea878a712720fbc7d",
    "firmware/ax25-classic1/apply_ax25_classic1_reserve.py": "04ded4879046a508cb3e179d0499cc6faec3784f",
    "firmware/ax25-rx1/AX25AFSKRX.cpp": "cf811dd953fdbbb7218eeb30079f8da12d04871a",
    "firmware/ax25-rx1/AX25AFSKRX.h": "c6059997d66d30af59a74a5085e4a60a7d50a90e",
    "firmware/ax25-rx1/apply_ax25_rx1.py": "3e6916e374bd1510d6acf80b3b0159c5666179a0",
    "firmware/ax25-rx2/apply_ax25_rx2.py": "590a044b057ddb56d7b47ec3a42de584d1c4826d",
    "firmware/ax25-rx3/apply_ax25_rx3.py": "bd49a33d62c025039e8d6f7a49cffb558eff1bda",
}
assert eng["files"] == expected_blobs

assert m["branding"]["legacy_version_token"] == "YWD-AX25R3-v0.2.2"
assert m["branding"]["legacy_info"] == "YWD-MMDVM-AX25R3"
assert m["branding"]["expected_info"] == "YWD-1278-AX25R3"
assert m["branding"]["expected_identity"] == (
    "MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

safety = m["safety"]
assert safety == {
    "hardware_access": False,
    "flash_enabled": False,
    "option_bytes_permitted": False,
    "rf_transmit_possible": False,
}

# Builder must use the frozen engineering Git object database, never its
# working tree, and apply transforms in manifest order.
assert 'git -C "$ENGINEERING_REPO" show "$ENG_COMMIT:$path"' in builder
assert 'ENGINEERING_WORKTREE_USED=NO' in builder
assert 'for rel in "${TRANSFORM_ORDER[@]}"' in builder
assert 'python3 "$TRANSFORMS/$rel" "$src"' in builder
assert 'python3 "$BRANDER" "$src" --manifest "$MANIFEST"' in builder
assert 'make -C "$src" -j"$JOBS" "$MAKE_TARGET"' in builder
assert 'UPSTREAM_HAT_BUILD_RECIPE=PASS' in builder

# No hardware or flasher command belongs in a build-only tool.
for forbidden in (
    "stm32flash",
    "pinctrl ",
    "raspi-gpio",
    "/dev/ttyAMA0",
    "/dev/serial0",
    "flash.sh",
    "qualify-roundtrip.sh",
    "sudo ",
):
    assert forbidden not in builder, forbidden

# Product branding must be identity-only after the exact frozen AX25R3 chain.
assert "FROZEN_AX25R3_BEHAVIOR_ANCHORS=PASS" in brander
assert "BEHAVIORAL_CHANGES_AFTER_FROZEN_AX25R3=NONE" in brander
assert "0x000E006FU" in brander
assert "CIO_FIFO_RESERVE = 256U" in brander
assert "YWD_RF_TX_TONES" in brander
assert "reply[4U] = 3U" in brander

print("PACKET_FIRMWARE_BUILD_CONTRACT=PASS")
print("FROZEN_ENGINEERING_COMMIT=PASS")
print("FROZEN_ENGINEERING_BLOBS=12")
print("TRANSFORM_ORDER=PASS")
print("STM32_HSE_HZ=8000000")
print("ADF7021_TCXO_HZ=14745600")
print("OSC_OVERRIDE=NO")
print("BUILD_HARDWARE_ACCESS=NO")
print("BUILD_RF_TRANSMIT=NO")
print("BUILD_FLASH_WRITE=NO")
print("OPTION_BYTES_WRITTEN=NO")
