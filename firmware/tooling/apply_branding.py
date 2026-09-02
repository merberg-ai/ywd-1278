#!/usr/bin/env python3
"""Apply the 0B-P1 YWD-1278 identity transform to exact pinned MMDVM_HS.

This transform is intentionally tiny. It requires the exact upstream commit,
exact upstream version.h blob, and an exact copy of the pinned simplex-HAT
configuration. It changes only version.h; Config.h is the generated build
configuration copied by the wrapper from configs/MMDVM_HS_Hat.h.

No hardware is accessed by this program.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


def git(src: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(src), *args], text=True).strip()


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise RuntimeError("unsupported firmware build manifest schema")
    return data


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one pristine anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply YWD-1278 firmware branding to pinned upstream source")
    ap.add_argument("source")
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()

    src = Path(args.source).resolve()
    manifest = load_manifest(Path(args.manifest).resolve())
    upstream = manifest["upstream"]
    branding = manifest["branding"]

    expected_commit = upstream["commit"]
    if git(src, "rev-parse", "HEAD") != expected_commit:
        raise RuntimeError("source checkout is not the pinned upstream commit")

    version_path = src / "version.h"
    template_path = src / upstream["config_template"]
    config_path = src / "Config.h"
    if not version_path.is_file() or not template_path.is_file() or not config_path.is_file():
        raise RuntimeError("required upstream firmware source/configuration files are missing")

    if git(src, "hash-object", "version.h") != upstream["version_blob"]:
        raise RuntimeError("version.h does not match the pinned upstream blob")
    if git(src, "hash-object", upstream["config_template"]) != upstream["config_template_blob"]:
        raise RuntimeError("simplex-HAT configuration template does not match the pinned upstream blob")
    if config_path.read_bytes() != template_path.read_bytes():
        raise RuntimeError("Config.h is not an exact copy of the pinned simplex-HAT configuration")

    fw_version = branding["firmware_version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9._-]+)?", fw_version):
        raise RuntimeError("firmware_version is not in the expected product-version form")

    original = '#define DESCRIPTION     BOARD_INFO "-" FW_VERSION " " TCXO_FREQ "MHz " RF_DUAL RF_CHIP " FW by CA6JAU"'
    branded = (
        '#define DESCRIPTION     BOARD_INFO "-YWD-1278-v'
        + fw_version
        + ' " TCXO_FREQ "MHz " RF_DUAL RF_CHIP " FW based on CA6JAU"'
    )

    version = version_path.read_text(encoding="utf-8")
    version = replace_once(version, original, branded, "firmware DESCRIPTION")
    version_path.write_text(version, encoding="utf-8")

    changed = git(src, "diff", "--name-only").splitlines()
    if changed != ["Config.h", "version.h"]:
        raise RuntimeError(f"unexpected tracked firmware changes after branding: {changed}")
    if config_path.read_bytes() != template_path.read_bytes():
        raise RuntimeError("Config.h changed during branding transform")
    subprocess.check_call(["git", "-C", str(src), "diff", "--check"])

    print("YWD1278_BRANDING_TRANSFORM=PASS")
    print(f"UPSTREAM_COMMIT={expected_commit}")
    print(f"FIRMWARE_VERSION={fw_version}")
    print("TRACKED_CHANGES=Config.h,version.h")
    print("BEHAVIORAL_CHANGES=NONE")
    print("RF_CONFIGURED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
