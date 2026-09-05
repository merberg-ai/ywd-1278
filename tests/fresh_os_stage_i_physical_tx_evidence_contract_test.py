#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-tx-acceptance.json"
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-tx-target-pi.json"
DRY_RUN = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-dry-run-target-pi.json"
HARNESS = ROOT / "tools/qualify_stage_i_single_tx.py"

EXPECTED_HARNESS_BLOB = "1497d7d5b6badad778f3202b8783a24920469615"
EXPECTED_DRY_RUN_BLOB = "a222fc28eba2b5e6355dc0c60260d9c8133c66fb"
EXPECTED_EVIDENCE_BLOB = "9db56a496a8618e9159a9c6090503aa55d6967f5"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert d["schema"] == 1 and d["stage"] == "I"
    assert d["status"] == "target-pi-physical-tx-qualified"
    assert d["stage_i_complete"] is True

    put = d["product_under_test"]
    assert put["installed_commit"] == "2f5299e65add072fea6ee55a54dc421faf00c276"
    assert put["frequency_hz"] == 145050000
    assert put["tx_power"] == 200
    assert put["firmware_sha256"] == "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"

    vector = d["fixed_vector"]
    assert vector["source"] == "KJ6YWD-10"
    assert vector["destination"] == "YWD127"
    assert vector["path"] == []
    assert vector["information"] == "YWD-1278 STAGE-I TX 1/1"
    assert vector["kiss_body_bytes"] == 39
    assert vector["kiss_body_sha256"] == "7ce21d988402ca554cbb7f8c4626cddda9f8f2b970bb53a79ccf2264be67e7e2"

    tx = d["physical_tx"]
    assert tx["kiss_data_injected"] == 1
    assert tx["tx_dispatches"] == 1
    assert tx["tx_queue_accepted"] == 1
    assert tx["tx_queue_dispatched"] == 1
    assert tx["automatic_tx_retry"] is False
    assert tx["no_second_internal_dispatch_after_hold"] is True
    assert tx["operator_confirmed_independent_exact_decode"] is True
    assert tx["independent_external_decode_count"] == 1
    assert tx["independent_decoder_raw_log_archived"] is False

    rx = d["post_tx_rx"]
    assert rx["resumed"] is True
    assert rx["frame_bytes"] == 73
    assert rx["source"] == "KJ6YWD"
    assert rx["source_differs_from_stage_i_tx_source"] is True
    assert rx["final_tx_dispatches"] == 1
    assert rx["tx_queue_depth_final"] == 0
    assert rx["subscriber_drops_final"] == 0
    assert rx["tx_access_timeouts_final"] == 0
    assert rx["tx_downstream_failures_final"] == 0

    cleanup = d["cleanup_and_safety"]
    assert cleanup["persistent_tx_enabled_final"] is False
    assert cleanup["persistent_config_mutated"] is False
    assert cleanup["normal_service_restored"] is True
    assert cleanup["automatic_tx_retry"] is False
    assert cleanup["flash_written"] is False
    assert cleanup["option_bytes_written"] is False

    assert m["status"] == "physically-qualified"
    assert m["stage_i_complete"] is True
    assert m["operator_authorization"]["authorization_consumed"] is True
    assert m["physical"]["evidence_blob"] == EXPECTED_EVIDENCE_BLOB
    assert m["physical"]["qualified"] is True
    assert m["physical"]["internal_tx_dispatches"] == 1
    assert m["physical"]["independent_external_decode_count"] == 1
    assert m["physical"]["post_tx_rx_observed"] is True
    assert m["physical"]["persistent_tx_enabled_final"] is False
    assert m["physical"]["normal_service_restored"] is True

    assert blob(HARNESS) == EXPECTED_HARNESS_BLOB
    assert blob(DRY_RUN) == EXPECTED_DRY_RUN_BLOB
    assert blob(EVIDENCE) == EXPECTED_EVIDENCE_BLOB

    print("STAGE_I_PHYSICAL_TX_EVIDENCE=PASS")
    print("KISS_DATA_INJECTED=1")
    print("INTERNAL_TX_DISPATCHES=1")
    print("OPERATOR_CONFIRMED_INDEPENDENT_EXACT_DECODE=YES")
    print("POST_TX_RX_RESUMED=YES")
    print("QUEUE_AND_SUBSCRIBER_FAILURE_COUNTERS=ZERO")
    print("PERSISTENT_TX_ENABLED_FINAL=NO")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("FLASH_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
