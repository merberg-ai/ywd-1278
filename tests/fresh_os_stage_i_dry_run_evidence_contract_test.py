#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-dry-run-target-pi.json"
HARNESS = ROOT / "tools/qualify_stage_i_single_tx.py"

EXPECTED_HEAD = "0b0e288e619368f2b3d8928e241efd806b2df442"
EXPECTED_INSTALLED = "2f5299e65add072fea6ee55a54dc421faf00c276"
EXPECTED_HARNESS_BLOB = "1497d7d5b6badad778f3202b8783a24920469615"
EXPECTED_VECTOR_SHA = "7ce21d988402ca554cbb7f8c4626cddda9f8f2b970bb53a79ccf2264be67e7e2"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert d["schema"] == 1
    assert d["stage"] == "I"
    assert d["status"] == "target-pi-dry-run-qualified-physical-tx-pending"
    assert d["checkpoint_under_test"]["sha"] == EXPECTED_HEAD
    assert d["product_under_test"]["installed_commit"] == EXPECTED_INSTALLED
    assert d["product_under_test"]["frequency_hz"] == 145050000
    assert d["product_under_test"]["tx_power"] == 200
    assert d["product_under_test"]["persistent_tx_enabled"] is False
    assert d["product_under_test"]["automatic_flash_enabled"] is False

    checkout = d["checkout_recovery"]
    assert checkout["expected_head"] == EXPECTED_HEAD
    assert checkout["fetched_head"] == EXPECTED_HEAD
    assert checkout["commit_object_present"] is True
    assert checkout["tree_object_present"] is True
    assert checkout["harness_present"] is True
    assert checkout["checkout_result"] == "pass"
    assert checkout["child_exit_code"] == 0
    assert checkout["putty_session_survived"] is True

    vector = d["fixed_vector"]
    assert vector["source"] == "KJ6YWD-10"
    assert vector["destination"] == "YWD127"
    assert vector["path"] == []
    assert vector["information"] == "YWD-1278 STAGE-I TX 1/1"
    assert vector["kiss_body_bytes"] == 39
    assert vector["kiss_body_sha256"] == EXPECTED_VECTOR_SHA
    assert vector["maximum_kiss_data_messages"] == 1
    assert vector["automatic_tx_retry"] is False

    dry = d["dry_run"]
    assert dry["result"] == "pass"
    assert dry["exit_code"] == 0
    assert dry["service_mutated"] is False
    assert dry["modem_uart_opened"] is False
    assert dry["kiss_data_sent"] is False
    assert dry["rf_transmitted"] is False
    assert dry["persistent_config_mutated"] is False
    assert dry["beacon_enabled"] is False
    assert dry["flash_permitted"] is False
    assert dry["option_bytes_permitted"] is False
    assert dry["putty_session_survived"] is True

    auth = d["authorization"]
    assert auth["stage_i_one_shot_authorization_still_unused"] is True
    assert auth["physical_tx_attempted"] is False
    assert auth["physical_tx_qualified"] is False

    assert blob(HARNESS) == EXPECTED_HARNESS_BLOB

    print("STAGE_I_TARGET_PI_DRY_RUN_EVIDENCE=PASS")
    print(f"CHECKPOINT_HEAD={EXPECTED_HEAD}")
    print("ONE_SHOT_AUTHORIZATION_CONSUMED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
