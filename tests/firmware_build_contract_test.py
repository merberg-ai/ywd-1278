#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware" / "tooling" / "build-manifest.json"
TARGETS = ROOT / "firmware" / "targets.json"
BUILDER = ROOT / "firmware" / "build-ywd1278.sh"

m = json.loads(MANIFEST.read_text(encoding="utf-8"))
t = json.loads(TARGETS.read_text(encoding="utf-8"))
assert m["schema"] == 1
assert m["phase"] == "0B-P1"
assert m["upstream"]["commit"] == "7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5"
assert m["upstream"]["submodules"]["STM32F10X_Lib"] == "1debc23063f3942608e2bd62d04d5e1249c47fa3"
assert m["upstream"]["config_template"] == "configs/MMDVM_HS_Hat.h"
assert m["upstream"]["config_template_blob"] == "1c526b41dd96ea68823f2e83442a8a76fd59590a"
assert m["upstream"]["version_blob"] == "4239a854ec09ee90847468f931e1455ee461e2de"
assert m["build"]["make_target"] == "hs"
assert m["build"]["osc_hz"] == 14745600
assert m["safety"] == {
    "hardware_access": False,
    "flash_enabled": False,
    "option_bytes_permitted": False,
    "rf_transmit_possible": False,
}

matches = [x for x in t["targets"] if x["id"] == m["target_id"]]
assert len(matches) == 1
target = matches[0]
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["firmware_artifact"].endswith("MMDVM_HS_Hat-YWD-1278-v0.1.0-alpha0-7ff74ed.bin")
assert target["firmware_sha256"] == "db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3"
assert m["branding"]["expected_identity"].startswith(target["ywd1278_identity_prefix"])

builder = BUILDER.read_text(encoding="utf-8")
# The 0B-P1 build wrapper must remain physically incapable of touching the HAT.
for forbidden in ("stm32flash", "pinctrl", "/dev/tty", "/dev/serial", "systemctl reboot", "gpiochip"):
    assert forbidden not in builder, f"build-only pipeline contains forbidden hardware operation token: {forbidden}"

# A normal branch clone is not a strong enough source contract for an old pin.
# The builder must explicitly fetch the exact manifest commit and verify that
# both its commit object and tree object are locally present before checkout.
assert 'git init -q "$SEED"' in builder
assert 'fetch --quiet --no-tags --depth=1 origin "$UPSTREAM_COMMIT"' in builder
assert 'cat-file -e "$UPSTREAM_COMMIT^{commit}"' in builder
assert 'cat-file -e "$UPSTREAM_COMMIT^{tree}"' in builder
assert 'git clone --quiet --no-checkout' not in builder

print("FIRMWARE_BUILD_CONTRACT=PASS")
print("UPSTREAM_PIN=PASS")
print("EXACT_COMMIT_FETCH=PASS")
print("SUBMODULE_PIN=PASS")
print("QUALIFIED_ARTIFACT_HASH=PASS")
print("FLASH_GATE_CLOSED=PASS")
print("HARDWARE_ACCESS_PATH=ABSENT")
