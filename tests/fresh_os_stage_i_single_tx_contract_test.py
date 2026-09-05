#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_stage_i_single_tx.py"
STAGE_H_EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json"

EXPECTED_INSTALLED_COMMIT = "2f5299e65add072fea6ee55a54dc421faf00c276"
EXPECTED_STAGE_H_CHECKPOINT = "e7e203ba6ef76a0465ff6c25ef9671a46a4ab582"
EXPECTED_FIRMWARE_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_IDENTITY = "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
EXPECTED_STAGE_H_EVIDENCE_BLOB = "b4f32d40184bb4ce74a7d786940638583beab04d"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def assigned_constant(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing constant {name}")


def main() -> int:
    text = HARNESS.read_text(encoding="utf-8")
    tree = ast.parse(text)

    assert assigned_constant(tree, "EXPECTED_INSTALLED_COMMIT") == EXPECTED_INSTALLED_COMMIT
    assert assigned_constant(tree, "EXPECTED_FIRMWARE_SHA256") == EXPECTED_FIRMWARE_SHA
    assert assigned_constant(tree, "EXPECTED_IDENTITY") == EXPECTED_IDENTITY
    assert assigned_constant(tree, "EXPECTED_FREQUENCY_HZ") == 145_050_000
    assert assigned_constant(tree, "TX_POWER") == 200
    assert assigned_constant(tree, "AUTHORIZATION_TOKEN") == "STAGE-I-TX-145050-ONE"
    assert assigned_constant(tree, "ARM_PHRASE") == "TRANSMIT-STAGE-I-ONE"
    assert assigned_constant(tree, "EXTERNAL_PHRASE") == "EXTERNAL-DECODE-MATCH-ONE"
    assert assigned_constant(tree, "DESTINATION") == "YWD127"
    assert assigned_constant(tree, "INFORMATION") == "YWD-1278 STAGE-I TX 1/1"
    assert 'PERSISTENT_CONFIG = Path("/etc/ywd-1278/config.toml")' in text

    # Exactly one application-originated KISS DATA send exists in the physical path.
    assert text.count("kiss.sendall(encode(body, command=DATA))") == 1
    assert "KISS_DATA_MESSAGES=1" in text
    assert "AUTOMATIC_TX_RETRY=NO" in text
    assert "NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS" in text
    assert "INTERNAL_TX_DISPATCH_COUNT=1" in text
    assert "path=[]" in text

    # Persistent appliance must enter and leave Stage I in no-TX/no-auto-flash mode.
    assert "persistent TX must be disabled before Stage I" in text
    assert "automatic flash must remain disabled" in text
    assert "beacon must remain disabled" in text
    assert "PERSISTENT_CONFIG_MUTATED=NO" in text
    assert "PERSISTENT_TX_ENABLED=NO" in text
    assert "NORMAL_SERVICE_RESTORED=YES" in text
    assert "TEMP_CONFIG.write_text" in text
    assert "PERSISTENT_CONFIG.write" not in text

    # Temporary TX capability is restricted to /run and the qualified profile.
    assert 'TEMP_ROOT = Path("/run/ywd-1278-stage-i")' in text
    assert assigned_constant(tree, "TEMP_KISS_PORT") == 18001
    assert assigned_constant(tree, "TEMP_CONSOLE_PORT") == 18010
    assert assigned_constant(tree, "TEMP_PTY") == "/run/ywd-1278-stage-i/tnc"
    assert 'replace_toml_key(text, "radio", "tx_power", str(TX_POWER))' in text
    assert 'replace_toml_key(text, "radio", "tx_enabled", "true")' in text
    assert "load_product_packet_engine_config(TEMP_CONFIG)" in text

    # No firmware write/reset/automatic TX surface exists in the Stage-I harness.
    forbidden = (
        "stm32flash",
        "flash.sh",
        "WRITE-FIRMWARE-NOW",
        "hat_control.py",
        "application-release",
        "BOOT0",
        "systemctl enable",
        "BEACON ON",
        "UNPROTO",
        "CONNECT ",
    )
    for token in forbidden:
        assert token not in text, token

    # RX restart and post-TX integrity are mandatory before success.
    assert "WAITING_FOR_LATER_NON_QUALIFICATION_PACKET_145050=YES" in text
    assert "recv_post_tx_non_qualification" in text
    assert "POST_TX_RX_RESUMED=PASS" in text
    assert "SUBSCRIBER_DROPS_FINAL=0" in text
    assert "TX_ACCESS_TIMEOUTS_FINAL=0" in text
    assert "TX_DOWNSTREAM_FAILURES_FINAL=0" in text
    assert "TX_QUEUE_DEPTH_FINAL=0" in text

    # Stage H remains frozen and is the only base from which Stage I may proceed.
    actual_blob = blob(STAGE_H_EVIDENCE)
    assert actual_blob == EXPECTED_STAGE_H_EVIDENCE_BLOB, (actual_blob, EXPECTED_STAGE_H_EVIDENCE_BLOB)

    print("STAGE_I_SINGLE_TX_CONTRACT=PASS")
    print(f"BASE_STAGE_H_CHECKPOINT={EXPECTED_STAGE_H_CHECKPOINT}")
    print(f"INSTALLED_PRODUCT_COMMIT={EXPECTED_INSTALLED_COMMIT}")
    print("PERSISTENT_TX_DEFAULT=DISABLED")
    print("PHYSICAL_TX_AUTHORITY=ONE_SHOT_ONLY")
    print("AUTOMATIC_RETRY=NO")
    print("FIRMWARE_WRITE_AUTHORITY=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
