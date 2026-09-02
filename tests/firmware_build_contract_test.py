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
assert m["phase"] == "0B-P1R1"
assert m["profile_id"] == "0b-p1r1-stm32f103-simplex-adf7021-14.7456tcxo-8mhz-hse"
assert m["upstream"]["commit"] == "7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5"
assert m["upstream"]["submodules"]["STM32F10X_Lib"] == "1debc23063f3942608e2bd62d04d5e1249c47fa3"
assert m["upstream"]["config_template"] == "configs/MMDVM_HS_Hat.h"
assert m["upstream"]["config_template_blob"] == "1c526b41dd96ea68823f2e83442a8a76fd59590a"
assert m["upstream"]["version_blob"] == "4239a854ec09ee90847468f931e1455ee461e2de"
assert m["upstream"]["makefile_blob"] == "c73834e9734e4b74bd375cb98ce5144c31134de6"
assert m["upstream"]["build_script_blob"] == "30257c0aea66695ed32877b8688daa835ee4f0e2"
assert m["build"]["make_target"] == "hs"
assert m["build"]["stm32_hse_hz"] == 8000000
assert m["build"]["osc_override"] is False
assert m["rf"]["tcxo_hz"] == 14745600
assert m["supersedes"]["artifact_sha256"] == "db23bc84bd31828d8fb29d8e4164879b9e5e57a4b2ef2eb58c598c66a38420b3"
assert "incorrectly used ADF7021 14.7456 MHz TCXO as STM32 HSE" in m["supersedes"]["reason"]
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
assert target["qualification_write"]["enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["stm32_hse_hz"] == 8000000
assert target["tcxo_mhz"] == 14.7456
assert target["firmware_artifact"] is None
assert target["firmware_sha256"] is None
assert target["firmware_identity"] is None
assert any(x["sha256"] == m["supersedes"]["artifact_sha256"] for x in target["revoked_artifacts"])
assert m["branding"]["expected_identity"].startswith(target["ywd1278_identity_prefix"])

builder = BUILDER.read_text(encoding="utf-8")
# The build wrapper must remain physically incapable of touching the HAT.
for forbidden in ("stm32flash", "pinctrl", "/dev/tty", "/dev/serial", "systemctl reboot", "gpiochip"):
    assert forbidden not in builder, f"build-only pipeline contains forbidden hardware operation token: {forbidden}"

# Exact source/build-recipe pins are mandatory.
assert 'git init -q "$SEED"' in builder
assert 'fetch --quiet --no-tags --depth=1 origin "$UPSTREAM_COMMIT"' in builder
assert 'cat-file -e "$UPSTREAM_COMMIT^{commit}"' in builder
assert 'cat-file -e "$UPSTREAM_COMMIT^{tree}"' in builder
assert 'hash-object Makefile' in builder
assert 'hash-object "$UPSTREAM_BUILD_SCRIPT"' in builder
assert "UPSTREAM_HAT_BUILD_RECIPE=PASS" in builder
assert "^CLK_DEF=8000000$" in builder

# Critical regression gate: the 14.7456 MHz ADF7021 TCXO must never be passed
# to make as the STM32 OSC/HSE. Correct build follows upstream's no-override
# HAT recipe and therefore uses CLK_DEF=8000000.
assert 'make -C "$src" -j"$JOBS" "$MAKE_TARGET"' in builder
assert 'OSC="$' not in builder
assert 'osc_override=false' in builder
assert 'STM32_HSE_HZ=%s' in builder
assert 'ADF7021_TCXO_HZ=%s' in builder

# Published artifacts are intentionally 0444. Re-running the builder must not
# attempt to truncate those files in place. It must stage a new artifact and
# metadata in the same directory and atomically rename them into place.
assert 'FINAL_TMP="$OUT_DIR/.${ARTIFACT_NAME}.tmp.$$"' in builder
assert 'META_TMP="$OUT_DIR/.build-metadata.json.tmp.$$"' in builder
assert 'cp "$A" "$FINAL_TMP"' in builder
assert 'chmod 0444 "$FINAL_TMP" "$META_TMP"' in builder
assert 'mv -f "$FINAL_TMP" "$FINAL"' in builder
assert 'mv -f "$META_TMP" "$META"' in builder
assert 'ATOMIC_PUBLISH=PASS' in builder
assert 'cp "$A" "$FINAL"' not in builder

print("FIRMWARE_BUILD_CONTRACT=PASS")
print("UPSTREAM_PIN=PASS")
print("EXACT_COMMIT_FETCH=PASS")
print("SUBMODULE_PIN=PASS")
print("UPSTREAM_BUILD_RECIPE_PIN=PASS")
print("STM32_HSE_8MHZ=PASS")
print("ADF7021_TCXO_14_7456MHZ=PASS")
print("OSC_OVERRIDE=ABSENT")
print("READ_ONLY_ARTIFACT_REPUBLISH=PASS")
print("FAILED_P1_ARTIFACT=REVOKED")
print("P3_WRITE_GATE=CLOSED")
print("FLASH_GATE_CLOSED=PASS")
print("HARDWARE_ACCESS_PATH=ABSENT")
