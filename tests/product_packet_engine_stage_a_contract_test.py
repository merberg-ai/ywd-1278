#!/usr/bin/env python3
"""Freeze the first YWD-1278 product packet-engine component boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/qualification/0b-product-packet-engine-stage-a.json"

EXPECTED_COMPONENTS = {
    "src/ywd1278/ax25/__init__.py": "c35b8a99d9689a182752dbeb63c7ed70ed206912",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/phy/__init__.py": "020bb229e1cdd4a8a61cec90e85b60a537572ddb",
    "src/ywd1278/phy/bell202_rx.py": "18fae685a0accdeb2eb425793632cf123f45bbda",
    "src/ywd1278/phy/bell202_tx.py": "39677faa3302a74da9fbae6fa858899e54f1874f",
    "src/ywd1278/modem/__init__.py": "8e5d7f645a6b0df410f48e4083babeef977a316a",
    "src/ywd1278/modem/_serial.py": "c671633a9c0934cbc8206957eafc1d5736537fc7",
    "src/ywd1278/modem/owner.py": "012a34d3ff65c14f2f29e3954ae304d3ee281f9a",
    "src/ywd1278/modem/protocol.py": "1a923c81a90f4a9f782c3b21c321ace67cc8cd27",
    "src/ywd1278/modem/rx_config.py": "a671c07ddca83d4c0b061568bc48fb29e386c632",
    "src/ywd1278/modem/tx_config.py": "895ecc609c5490736f3c267d613c7bd3fa536a41",
    "src/ywd1278/modem/tx_owner.py": "d32763473a1eba89566ed512e9ab5fc7de575480",
    "src/ywd1278/kiss/__init__.py": "dd235f04835543fe16eb4d9f29c6ecb8b9a2e79e",
    "src/ywd1278/kiss/framing.py": "7227e68b6829099580f72f2a49fe0e68fbce1363",
    "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
    "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/kiss/tx_backend.py": "e06c1a619a02ecb4cf2073a3f270be1b2d54ea0e",
    "src/ywd1278/kiss/sustained.py": "63cf33f4b6d4cedd091af0349a8037669d45e84d",
    "src/ywd1278/tx/__init__.py": "3902944d12d3d8eb2b9ebfc5c52ef0549288c71d",
    "src/ywd1278/tx/broker.py": "1e3307dccea4f2805d32cb9be5b34f3537e29c4f",
    "src/ywd1278/tx/channel_access.py": "398af9158875c6ac063d0264c150086df009e555",
    "src/ywd1278/tx/channel_busy.py": "46c655a6d9143ac9ea21cbccb36caf77c4a14cd8",
    "src/ywd1278/tx/contextual.py": "c9de1ed7e751d6d96eadc4f6ac7b027cfe859012",
    "src/ywd1278/tx/csma.py": "b21925be0799d6d6ee887ba6dbb494014d50c710",
    "src/ywd1278/tx/half_duplex.py": "d826fd4a53d52ba359eb0b45642370db0f0cb7cc",
    "src/ywd1278/tx/txdelay.py": "b8035a58c4b48765c580dab06bcdb054a9801c8c",
    "src/ywd1278/service/__init__.py": "7336134297675de834ed53395e62d641b0020f1d",
    "src/ywd1278/service/tnc_runtime.py": "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1",
}

EXPECTED_PROOFS = {
    "firmware/qualification/0c-p2-rssi-live-physical-evidence.json": "8b293ff07afc235718003d32ebcae32bd09fbff2",
    "firmware/qualification/0c-p7-live-kiss-one-shot-physical-evidence.json": "027478487155e41c44885d37ee93efbd284dd129",
    "firmware/qualification/0c-p8-sustained-kiss-tnc-host.json": "f5c2828ca10491deaac81526eb6ef1e281068564",
    "firmware/qualification/0c-p8-r3-live-physical-evidence.json": "0c694c2fe8e4e1d21776117b662d30fdc9929fea",
}

EXPECTED_CONTRACTS = {
    "tests/sustained_kiss_tnc_contract_test.py": "fa49c652cb2ca86c01a1e9c4c2244d30c4c6b83e",
    "tests/sustained_kiss_tnc_integration_test.py": "83002be87a71913c3f145fc988fd883665a9764a",
    "tests/sustained_kiss_queue_concurrency_test.py": "ae8967afb30b7922e877874bf466a5ee0b40c55c",
    "tests/live_p8_r3_physical_evidence_contract_test.py": "fd34003a77cee3a4a2dff4dca3f7dbb6cdf53130",
    "tests/live_p7_kiss_one_shot_evidence_contract_test.py": "13df20c1430b1a5054b63f40227ad6aaf4ff7051",
}

EXPECTED_EXCLUDED = {
    "src/ywd1278/tx/access_queue.py",
    "src/ywd1278/tx/rssi_analysis.py",
    "src/ywd1278/service/live_channel_access.py",
    "src/ywd1278/service/rx_runtime.py",
}

FIRMWARE_SHA256 = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 "
    "FW based on CA6JAU GitID #7ff74ed"
)


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema"] == 1
    assert manifest["phase"] == "0B-product-packet-engine-stage-a"
    assert manifest["stage"] == "first-product-packet-engine-component-freeze"
    assert manifest["status"] in {"staged", "qualified"}
    assert manifest["base_checkpoint"] == {
        "branch": "checkpoint/pre-fresh-install-flash-run",
        "sha": "383de08ede7b452fc773bc5cb6803e4a5acd39cf",
    }

    assert manifest["component_count"] == len(EXPECTED_COMPONENTS) == 29
    assert manifest["components"] == EXPECTED_COMPONENTS
    assert set(manifest["excluded_from_product_graph"]) == EXPECTED_EXCLUDED
    assert not (set(EXPECTED_COMPONENTS) & EXPECTED_EXCLUDED)
    assert "src/ywd1278/daemon.py" not in EXPECTED_COMPONENTS

    for relative, expected in EXPECTED_COMPONENTS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"product packet-engine drift: {relative}: {actual} != {expected}"

    flattened_proofs = {
        value["path"]: value["blob"] for value in manifest["proof_anchors"].values()
    }
    assert flattened_proofs == EXPECTED_PROOFS
    for relative, expected in EXPECTED_PROOFS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"qualification proof drift: {relative}: {actual} != {expected}"

    flattened_contracts = {
        value["path"]: value["blob"] for value in manifest["qualification_contracts"].values()
    }
    assert flattened_contracts == EXPECTED_CONTRACTS
    for relative, expected in EXPECTED_CONTRACTS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"qualification contract drift: {relative}: {actual} != {expected}"

    firmware = manifest["firmware_anchor"]
    assert firmware["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
    assert firmware["identity"] == EXPECTED_IDENTITY
    assert firmware["artifact_size_bytes"] == 59892
    assert firmware["artifact_sha256"] == FIRMWARE_SHA256
    assert firmware["programmed_readback_sha256"] == FIRMWARE_SHA256
    assert firmware["qualified_frequency_hz"] == 145_050_000
    assert firmware["qualified_tx_power"] == 200

    p2 = load("firmware/qualification/0c-p2-rssi-live-physical-evidence.json")
    assert p2["status"] == "physically-qualified-telemetry-only"
    assert p2["firmware"]["identity"] == EXPECTED_IDENTITY
    assert p2["firmware"]["artifact_sha256"] == FIRMWARE_SHA256
    assert p2["firmware"]["programmed_readback_sha256"] == FIRMWARE_SHA256
    assert p2["firmware"]["runtime_identity_verified"] is True
    assert p2["receive_observation"]["frequency_hz"] == 145_050_000
    assert p2["receive_observation"]["fifo_dropped_bytes"] == 0

    p7 = load("firmware/qualification/0c-p7-live-kiss-one-shot-physical-evidence.json")
    assert p7["status"] == "physically-qualified"
    assert p7["frequency_hz"] == 145_050_000
    assert p7["rf_power"] == 200
    assert p7["kiss_data_admitted"] == 1
    assert p7["tnc_appended_fcs_exactly_once"] is True
    assert p7["external_receiver"]["observed_exact_decodes"] == 1
    assert p7["rx_stop_tx_rx_restart"] is True
    assert p7["fifo_dropped_bytes"] == 0
    assert p7["duplicate_dispatch"] is False
    assert p7["automatic_tx_retry"] is False

    p8_host = load("firmware/qualification/0c-p8-sustained-kiss-tnc-host.json")
    assert p8_host["status"] == "host-qualified"
    for key in (
        "real_localhost_kiss_tcp",
        "real_p7_admission",
        "real_p2_p1_channel_access",
        "real_p4e_half_duplex",
        "real_p5_txdelay_broker",
        "real_tx_modem_owner",
        "single_modem_owner",
        "rx_fifo_backlog_priority_before_tx_access",
        "serialized_queue_clock_sampling",
    ):
        assert p8_host["architecture"][key] is True, key
    assert p8_host["qualification"]["sustained_tx_cycles"] == 4
    assert p8_host["qualification"]["queue_drains_to_zero"] is True
    assert p8_host["qualification"]["automatic_retry"] is False
    assert p8_host["qualification_evidence"]["final_exact_head_ci"] == "success"

    p8 = load("firmware/qualification/0c-p8-r3-live-physical-evidence.json")
    assert p8["status"] == "physically-qualified"
    assert p8["qualification_complete"] is True
    assert p8["frequency_hz"] == 145_050_000
    assert p8["rf_power"] == 200
    assert p8["kiss_data_admitted"] == 3
    assert p8["tx_submissions"] == 3
    assert p8["complete_rx_tx_rx_cycles"] == 3
    assert p8["external_direct_decode_required"] == 3
    assert p8["external_direct_decode_observed"] == 3
    assert p8["fifo_dropped_bytes"] == 0
    assert p8["rx_fifo_backlog_priority"] == "pass"
    assert p8["serialized_queue_clock_sampling"] == "pass"
    assert p8["single_modem_owner"] == "pass"
    assert p8["uart_released"] is True
    assert p8["duplicate_dispatch"] is False
    assert p8["automatic_tx_retry"] is False

    safety = manifest["safety"]
    for key in (
        "stage_a_component_changes",
        "stage_a_uart_access",
        "stage_a_rf_activity",
        "stage_a_flash_activity",
        "stage_a_gpio_activity",
        "stage_a_enables_daemon",
        "stage_a_enables_product_tx",
        "automatic_tx_retry",
    ):
        assert safety[key] is False, key
    assert safety["product_tx_authority_remains_construction_time_fail_closed"] is True

    print("YWD1278_STAGE_A_PRODUCT_PACKET_ENGINE_CONTRACT=PASS")
    print("PRODUCT_PACKET_ENGINE_COMPONENTS=29")
    print(f"PRODUCT_PACKET_ENGINE_BASE={manifest['base_checkpoint']['sha']}")
    print(f"AX25R4_SHA256={FIRMWARE_SHA256}")
    print("QUALIFIED_FREQUENCY_HZ=145050000")
    print("P8_HOST_SUSTAINED_GRAPH=PASS")
    print("P8_R3_PHYSICAL_RX_TX_RX=3_OF_3")
    print("P8_R3_EXTERNAL_DIRECT_DECODE=3_OF_3")
    print("FIFO_DROPS=ZERO")
    print("DUPLICATE_DISPATCH=NO")
    print("AUTOMATIC_TX_RETRY=NO")
    print("STAGE_A_UART_RF_FLASH_GPIO=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
