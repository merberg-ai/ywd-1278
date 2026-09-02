#!/usr/bin/env python3
"""Apply YWD-1278 product branding to the exact frozen AX25R3 tree.

This runs only after the complete d25180 engineering transform chain has
succeeded. It changes user-visible identity strings only; packet/RF behavior,
opcodes, timing, filtering, FIFO logic, and target configuration remain intact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

EXPECTED_TRACKED = [
    "ADF7021.cpp",
    "Config.h",
    "Globals.h",
    "IO.cpp",
    "IO.h",
    "IOSTM.cpp",
    "MMDVM_HS.cpp",
    "SerialPort.cpp",
    "version.h",
]
EXPECTED_UNTRACKED = [
    "AX25AFSKRX.cpp",
    "AX25AFSKRX.h",
    "AX25AFSKTX.cpp",
    "AX25AFSKTX.h",
]


def git_lines(src: Path, *args: str) -> list[str]:
    out = subprocess.check_output(["git", "-C", str(src), *args], text=True)
    return sorted(line for line in out.splitlines() if line)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()

    src = args.source.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    branding = manifest["branding"]
    legacy_version = branding["legacy_version_token"]
    legacy_info = branding["legacy_info"]
    expected_info = branding["expected_info"]
    firmware_version = branding["firmware_version"]
    new_version = f"YWD-1278-AX25R3-v{firmware_version}"

    if git_lines(src, "diff", "--name-only") != sorted(EXPECTED_TRACKED):
        raise RuntimeError("packet branding requires the exact frozen AX25R3 transformed tracked-file set")
    if git_lines(src, "ls-files", "--others", "--exclude-standard") != sorted(EXPECTED_UNTRACKED):
        raise RuntimeError("packet branding requires the exact frozen AX25R3 generated-file set")
    if (src / "Config.h").read_bytes() != (src / "configs/MMDVM_HS_Hat.h").read_bytes():
        raise RuntimeError("Config.h differs from the pinned simplex-HAT template")

    adf = (src / "ADF7021.cpp").read_text(encoding="utf-8")
    iostm = (src / "IOSTM.cpp").read_text(encoding="utf-8")
    tx = (src / "AX25AFSKTX.cpp").read_text(encoding="utf-8")
    serial_path = src / "SerialPort.cpp"
    version_path = src / "version.h"
    serial = serial_path.read_text(encoding="utf-8")
    version = version_path.read_text(encoding="utf-8")

    # Frozen behavior anchors from the physically-qualified AX25R3 lineage.
    required = [
        (legacy_version in version, "AX25R3 v0.2.2 engineering identity"),
        (legacy_info in serial, "AX25R3 engineering info string"),
        ("0x000E006FU" in adf, "Register-15 CDR bypass"),
        ("5U                         << 20" in adf, "RX3 post-demod filter"),
        ("TIM2" in iostm and "19200U" in iostm, "TIM2 19.2 ksps sampler"),
        ("CIO_FIFO_RESERVE = 256U" in tx, "qualified TX FIFO reserve"),
        ("YWD_RF_TX_TONES" in serial, "qualified explicit RF TX namespace"),
        ("YWD_RX_START" in serial and "YWD_RX_STATUS" in serial, "qualified YWD_RX namespace"),
        ("reply[4U] = 3U" in serial, "RX protocol revision 3"),
    ]
    missing = [label for ok, label in required if not ok]
    if missing:
        raise RuntimeError("frozen AX25R3 behavior anchor missing: " + ", ".join(missing))

    version = replace_once(version, legacy_version, new_version, "product firmware identity")
    serial = replace_once(serial, legacy_info, expected_info, "product info string")

    version_path.write_text(version, encoding="utf-8")
    serial_path.write_text(serial, encoding="utf-8")

    if git_lines(src, "diff", "--name-only") != sorted(EXPECTED_TRACKED):
        raise RuntimeError("product branding unexpectedly changed the transformed tracked-file set")
    if git_lines(src, "ls-files", "--others", "--exclude-standard") != sorted(EXPECTED_UNTRACKED):
        raise RuntimeError("product branding unexpectedly changed generated files")
    if (src / "Config.h").read_bytes() != (src / "configs/MMDVM_HS_Hat.h").read_bytes():
        raise RuntimeError("Config.h changed during product branding")

    subprocess.check_call(["git", "-C", str(src), "diff", "--check"])
    print("YWD1278_PACKET_BRANDING_TRANSFORM=PASS")
    print(f"LEGACY_VERSION_TOKEN={legacy_version}")
    print(f"PRODUCT_VERSION_TOKEN={new_version}")
    print(f"PRODUCT_INFO={expected_info}")
    print("FROZEN_AX25R3_BEHAVIOR_ANCHORS=PASS")
    print("BEHAVIORAL_CHANGES_AFTER_FROZEN_AX25R3=NONE")
    print("RF_CONFIGURED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
