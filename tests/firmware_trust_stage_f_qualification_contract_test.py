#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-firmware-trust-stage-f.json"

EXPECTED_IMPLEMENTATION = "3a976d6209752411b3a2823db6ffcc6ce341fd6a"
EXPECTED_RUN = 33878913819
EXPECTED_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_STOCK = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"


def git_blob(path: str) -> str:
    payload=(ROOT/path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode()+payload).hexdigest()


def main() -> int:
    d=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["phase"] == "fresh-install-stage-f-firmware-trust"
    assert d["status"] == "host-qualified-physical-rehearsal-pending"
    assert d["base_checkpoint"] == {
        "branch": "checkpoint/product-installer-runtime-stage-e-host-qualified",
        "sha": "73891a37c2d7de19aebb1f55bdd0324b121bbf02",
    }

    fw=d["product_firmware"]
    assert fw["artifact_size_bytes"] == 59892
    assert fw["artifact_sha256"] == EXPECTED_SHA
    assert fw["programmed_readback_bytes"] == 59892
    assert fw["programmed_readback_sha256"] == EXPECTED_SHA
    assert fw["expected_identity"] == (
        "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
        "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
    )
    stock=d["stock_rollback"]
    assert stock["required"] is True
    assert stock["flash_size_bytes"] == 131072
    assert stock["sha256"] == EXPECTED_STOCK
    assert stock["read_passes_required"] == 2
    assert stock["byte_identical_required"] is True
    assert stock["option_bytes_read_or_written"] is False

    implementation=d["implementation"]
    expected_blobs={
        implementation["profile_path"]: "b7263fbe7bde1ad547207b7cc0e4f22220b38f72",
        implementation["trust_path"]: "5f119de52a9363adcb10eab8e007a2cee8cab158",
        implementation["prepare_path"]: "35abcbe4fed888dcd4f8e422e2954fc13e8f1ded",
        implementation["deploy_path"]: "94adb8ddd4dfebd90a1ea105203afc6a5049e828",
        implementation["regression_path"]: "e6a97a46f7c6aae9390ebfb638634f92c1a8d1bb",
        implementation["contract_path"]: "6325ed29a828bd857d894a1d29e2cb87d25d04f2",
    }
    for path, expected in expected_blobs.items():
        assert git_blob(path) == expected, f"qualified Stage-F implementation drift: {path}"

    h=d["host_qualification"]
    assert h["qualified_implementation_head"] == EXPECTED_IMPLEMENTATION
    assert h["ci_run_id"] == EXPECTED_RUN
    assert h["ci_conclusion"] == "success"
    assert h["firmware_trust_regression_tests"] == 6
    for key in (
        "firmware_trust_regression",
        "architecture_contract",
        "packaged_trust_module_smoke",
        "stage_e_regression_preserved",
        "stage_e_contract_preserved",
        "stage_d_full_graph_preserved",
        "stage_c_behavior_preserved",
        "stage_a_freeze_preserved",
        "sustained_tnc_physical_evidence_preserved",
        "zero_io_daemon_self_test",
    ):
        assert h[key] == "pass", key

    policy=d["deployment_policy"]
    assert policy["runtime_readiness_must_be_ready"] is True
    assert policy["tx_must_be_disabled"] is True
    assert policy["automatic_flash_must_be_disabled"] is True
    assert policy["unknown_or_ambiguous_identity_fails_closed"] is True
    assert policy["verified_stock_backup_required_before_write"] is True
    assert policy["programmed_readback_required"] is True
    assert policy["exact_runtime_identity_required"] is True
    assert policy["already_exact_ax25r4_is_readback_verified_without_rewrite"] is True
    assert policy["option_bytes_permitted"] is False
    assert policy["rf_tx_permitted"] is False
    assert policy["service_enable_permitted"] is False

    assert d["hardware_activity"] == {
        "uart": False,
        "rf": False,
        "flash": False,
        "gpio": False,
        "option_bytes": False,
        "systemd_service_started": False,
    }
    physical=d["physical_stage_f"]
    assert physical["existing_pi_rehearsal_complete"] is False
    assert physical["programmed_readback_verified_by_stage_f_tool"] is False
    assert physical["service_eligibility_record_written_on_pi"] is False
    assert physical["flash_write_expected_on_current_pi"] is False

    print("YWD1278_STAGE_F_HOST_QUALIFICATION=PASS")
    print(f"QUALIFIED_IMPLEMENTATION_HEAD={EXPECTED_IMPLEMENTATION}")
    print(f"DEDICATED_CI_RUN={EXPECTED_RUN}_SUCCESS")
    print(f"AX25R4_ARTIFACT_SHA256={EXPECTED_SHA}")
    print(f"STOCK_ROLLBACK_SHA256={EXPECTED_STOCK}")
    print("PROTECTED_STOCK_BACKUP_REQUIRED=YES")
    print("PROGRAMMED_READBACK_REQUIRED=YES")
    print("EXACT_RUNTIME_IDENTITY_REQUIRED=YES")
    print("ALREADY_INSTALLED_AX25R4_REWRITE_REQUIRED=NO")
    print("SERVICE_ENABLE_AUTHORITY=ABSENT")
    print("PHYSICAL_STAGE_F=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
