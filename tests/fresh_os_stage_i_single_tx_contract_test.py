#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools/qualify_stage_i_single_tx.py"
STAGE_H_EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json"

EXPECTED_INSTALLED_COMMIT = "2f5299e65add072fea6ee55a54dc421faf00c276"
EXPECTED_STAGE_H_CHECKPOINT = "e7e203ba6ef76a0465ff6c25ef9671a46a4ab582"
EXPECTED_FIRMWARE_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_IDENTITY = "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"

# Immutable Stage-H final evidence blob at the Stage-I base boundary.
EXPECTED_STAGE_H_EVIDENCE_BLOB = "b4f32d40184bb4ce74a7d786940638583beab04d"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    text = HARNESS.read_text(encoding="utf-8")

    assert EXPECTED_INSTALLED_COMMIT in text
    assert EXPECTED_FIRMWARE_SHA in text
    assert EXPECTED_IDENTITY in text
    assert "EXPECTED_FREQUENCY_HZ = 145_050_000" in text
    assert "TX_POWER = 200" in text

    # Exact one-shot operator gates.
    assert 'AUTHORIZATION_TOKEN = "STAGE-I-TX-145050-ONE"' in text
    assert 'ARM_PHRASE = "TRANSMIT-STAGE-I-ONE"' in text
    assert 'EXTERNAL_PHRASE = "EXTERNAL-DECODE-MATCH-ONE"' in text
    assert text.count("kiss.sendall(encode(body, command=DATA))") == 1
    assert "KISS_DATA_MESSAGES=1" in text
    assert "AUTOMATIC_TX_RETRY=NO" in text
    assert "NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS" in text
    assert "INTERNAL_TX_DISPATCH_COUNT=1" in text

    # Direct UI frame: no digipeater path and a deterministic operator-visible vector.
    assert 'DESTINATION = "YWD127"' in text
    assert 'INFORMATION = "YWD-1278 STAGE-I TX 1/1"' in text
    assert "path=[]" in text

    # Persistent appliance must enter and leave Stage I in no-TX/no-auto-flash mode.
    assert 'PERSISTENT_CONFIG = Path("/etc/ywd-1278/config.toml")' in text
    assert "persistent TX must be disabled before Stage I" in text
    assert "automatic flash must remain disabled" in text
    assert "beacon must remain disabled" in text
    assert "PERSISTENT_CONFIG_MUTATED=NO" in text
    assert "PERSISTENT_TX_ENABLED=NO" in text
    assert "NORMAL_SERVICE_RESTORED=YES" in text
    assert ".write_text(temp_text" in text
    assert "TEMP_CONFIG.write_text" in text
    assert "PERSISTENT_CONFIG.write" not in text

    # Temporary TX capability is restricted to /run and the physically-qualified profile.
    assert 'TEMP_ROOT = Path("/run/ywd-1278-stage-i")' in text
    assert 'TEMP_KISS_PORT = 18001' in text
    assert 'TEMP_CONSOLE_PORT = 18010' in text
    assert 'TEMP_PTY = "/run/ywd-1278-stage-i/tnc"' in text
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
        "option bytes",
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
