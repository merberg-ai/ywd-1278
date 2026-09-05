#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-tx-acceptance.json"

EXPECTED = {
    "tools/qualify_stage_i_single_tx.py": "1497d7d5b6badad778f3202b8783a24920469615",
    "tests/fresh_os_stage_i_single_tx_test.py": "46b6aed22f97c40e7bc72d84263be542e028e505",
    "tests/fresh_os_stage_i_single_tx_contract_test.py": "f12dd6351bea39a4a24b10f136d8598098d1a2b9",
    "firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json": "b4f32d40184bb4ce74a7d786940638583beab04d",
}


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    d = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert d["schema"] == 1 and d["stage"] == "I"
    assert d["status"] == "host-qualified-physical-tx-pending"
    assert d["base_stage_h"]["sha"] == "e7e203ba6ef76a0465ff6c25ef9671a46a4ab582"
    assert d["product_under_test"]["installed_commit"] == "2f5299e65add072fea6ee55a54dc421faf00c276"
    assert d["product_under_test"]["frequency_hz"] == 145050000
    assert d["product_under_test"]["qualified_tx_power"] == 200

    h = d["host_qualification"]
    assert h["implementation_head"] == "911e7ac7b82de5a57df01ba2939babfe2984d236"
    assert h["ci_run_id"] == 33934803171
    assert h["ci_conclusion"] == "success"
    assert h["harness_blob"] == EXPECTED["tools/qualify_stage_i_single_tx.py"]
    assert h["regression_blob"] == EXPECTED["tests/fresh_os_stage_i_single_tx_test.py"]
    assert h["safety_contract_blob"] == EXPECTED["tests/fresh_os_stage_i_single_tx_contract_test.py"]
    assert h["implementation_workflow_blob"] == "8887b63662c08b76a81ca049bef29784a82f99a9"
    assert h["regression_tests"] == 5
    assert h["dry_run_zero_io"] is True
    assert h["hardware_uart_opened"] is False
    assert h["rf_transmitted"] is False
    assert h["flash_written"] is False

    auth = d["operator_authorization"]
    assert auth["stage_i_authorized"] is True
    assert auth["authorization_scope"] == "one physical product TX acceptance frame only"
    for key in (
        "persistent_tx_authorized",
        "automatic_tx_authorized",
        "beacon_tx_authorized",
        "connected_mode_tx_authorized",
        "firmware_write_authorized",
    ):
        assert auth[key] is False, key

    vector = d["fixed_vector"]
    assert vector == {
        "source": "KJ6YWD-10",
        "destination": "YWD127",
        "path": [],
        "information": "YWD-1278 STAGE-I TX 1/1",
        "kiss_data_includes_fcs": False,
        "tnc_appends_fcs": True,
        "maximum_kiss_data_messages": 1,
        "maximum_internal_tx_dispatches": 1,
        "automatic_retry": False,
        "requires_exactly_one_independent_external_decode": True,
    }

    assert d["runtime_policy"]["persistent_config_mutation_permitted"] is False
    assert d["runtime_policy"]["firmware_flash_permitted"] is False
    assert d["runtime_policy"]["option_bytes_permitted"] is False
    assert d["runtime_policy"]["gpio_reset_permitted"] is False
    assert d["physical"] == {
        "tx_attempted": False,
        "external_decode_observed": False,
        "post_tx_rx_observed": False,
        "qualified": False,
    }

    for path, expected in EXPECTED.items():
        actual = blob(ROOT / path)
        assert actual == expected, f"Stage-I frozen host boundary drift: {path}: {actual} != {expected}"

    print("STAGE_I_HOST_QUALIFICATION_EVIDENCE=PASS")
    print("PHYSICAL_TX=PENDING")
    print("AUTHORIZED_FRAME_COUNT=1")
    print("PERSISTENT_TX_AUTHORITY=NO")
    print("AUTOMATIC_RETRY=NO")
    print("FIRMWARE_WRITE_AUTHORITY=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
