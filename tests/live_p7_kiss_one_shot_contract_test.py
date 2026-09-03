#!/usr/bin/env python3
"""Static and manifest contract for the guarded 0C-P7 live KISS one-shot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "qualify_live_p7_kiss_one_shot.py"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p7-live-kiss-one-shot.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path],
        cwd=ROOT,
        text=True,
    ).strip()


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = HARNESS.read_text(encoding="utf-8")

    assert data["schema"] == 1
    assert data["phase"] == "0C-P7-live"
    assert data["stage"] == "kiss-originated-one-shot"
    assert data["status"] == "staged"
    assert data["base_checkpoint"] == "checkpoint/0c-p7-kiss-data-admission-host-qualified"
    assert data["base_checkpoint_sha"] == "3df9a46f0851876e55c078ab41504584304bef38"
    assert data["device"] == "/dev/ttyAMA0"
    assert data["frequency_hz"] == 145050000
    assert data["rf_power"] == 200
    assert data["packet_count"] == 1

    assert data["kiss_listener_host"] == "127.0.0.1"
    assert data["kiss_listener_port"] == 0
    assert data["kiss_listener_ephemeral"] is True
    assert data["kiss_listener_closed_before_channel_access_dispatch"] is True
    assert data["kiss_data_messages_required"] == 1
    assert data["kiss_data_payload_includes_fcs"] is False
    assert data["tnc_appends_fcs_exactly_once"] is True
    assert data["kiss_port"] == 0
    assert data["kiss_parameter_commands"] == {
        "txdelay": 30,
        "persist": 63,
        "slottime": 10,
    }
    assert data["expected_parameter_generation"] == 3

    assert data["source"] == "KJ6YWD-10"
    assert data["destination"] == "YWD7"
    assert data["path"] == ["YWDNOD"]
    assert data["information_text"] == "YWD-1278 P7 KISS VERIFY 1/1"
    assert data["kiss_body_bytes"] == 50
    assert data["kiss_body_sha256"] == "ab21f1684442a24693a4a8f35b0ef5febaa007703d67609005c31e99332ecef3"
    assert data["frame_with_fcs_bytes"] == 52
    assert data["frame_with_fcs_sha256"] == "a5aeebc7fb9dadeab9264a5deed8973b7b41a8acbdb2932a78e40dde814d2985"
    assert data["pre_flags"] == 45
    assert data["post_flags"] == 3
    assert data["selector_count"] == 801
    assert data["packed_selector_bytes"] == 101
    assert data["packed_selector_sha256"] == "82fff4f7b03ae787fb16d6d14cc9a59e81e7b3f751a3e4be1e090320d26b2b7f"
    assert data["samples_per_selector"] == 16
    assert data["expected_generated_samples"] == 12816

    assert data["requires_live_busy_before_dispatch"] is True
    assert data["requires_fresh_fcs_valid_rx_trigger_before_tx"] is True
    assert data["required_pre_tx_decoded_frames"] == 1
    assert data["qualification_randomness"] == {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }
    assert data["requires_rx_active_after_tx"] is True
    assert data["requires_final_non_qualification_fcs_valid_rx"] is True
    assert data["required_total_qualifying_non_p7_inbound_frames"] == 2
    assert data["p7_qualification_echo_must_not_count_as_rx_proof"] is True
    assert data["rx_fifo_dropped_bytes_required"] == 0
    assert data["maximum_transmit_submissions"] == 1
    assert data["automatic_tx_retry"] is False
    assert data["requires_direct_external_decode"] is True
    assert data["required_external_tx_decodes"] == 1
    assert data["require_ywdnod_repeated_decode"] is False
    assert data["confirmation_token"] == "P7-LIVE-KISS-145050-P200-ONE"
    assert data["interactive_phrase"] == "TRANSMIT-P7-KISS-ONE"
    assert data["product_tx_enabled"] is False
    assert data["persistent_kiss_tx_enabled"] is False
    assert data["flash_permitted"] is False
    assert data["gpio_reset_permitted"] is False
    assert data["option_bytes_permitted"] is False

    # The live gate must use the actual host-qualified P7 path, not reconstruct
    # its behavior with direct modem calls.
    for required in (
        "TNCTransmitBackend",
        "KISSDataAdmissionQueue",
        "TNCSessionState",
        "ContextualHalfDuplexSubmitter",
        "ContextualTXDelayRouter",
        "start_server_thread",
        "stop_server_thread",
        "encode(body, command=DATA)",
        "append_fcs(body)",
        "admission.observe_rssi",
        "owner.rx_start",
        "owner.rx_stop",
        "FINAL_POST_TX_RX_WINDOW=OPEN",
        "FINAL_P7_QUALIFICATION_ECHO_IGNORED_AS_RX_PROOF=YES",
        "DO_NOT_RERUN_FULL_P7_LIVE_HARNESS=YES",
    ):
        assert required in source, required

    # There is one fixed KISS DATA injection and a capacity-one admission queue.
    assert source.count("encode(body, command=DATA)") == 1
    assert "queue_capacity=1" in source
    assert "KISS_DATA_MESSAGES_RECEIVED=1" in source
    assert "KISS_DATA_ADMITTED=1" in source
    assert "RF_TRANSMITTED=YES_EXACTLY_ONE_KISS_ORIGINATED_BURST" in source

    # Dry-run returns before either the modem owner or localhost listener can be
    # constructed/opened.
    dry_run_marker = source.index('if not args.transmit:')
    owner_construct = source.index('owner = TXModemOwner(')
    listener_call = source.index('kiss_port = inject_exactly_one_kiss_message(')
    assert dry_run_marker < owner_construct < listener_call
    assert 'KISS_LISTENER_OPENED=NO' in source[dry_run_marker:owner_construct]
    assert 'HARDWARE_UART_OPENED=NO' in source[dry_run_marker:owner_construct]
    assert 'RF_TRANSMITTED=NO' in source[dry_run_marker:owner_construct]

    # The server-injection function must close the listener before main reaches
    # the access window and begins RSSI scheduling.
    injection_function = source.index("def inject_exactly_one_kiss_message(")
    injection_stop = source.index("stop_server_thread(server, thread)", injection_function)
    access_window = source.index('print("P7_TX_ACCESS_WINDOW=OPEN")')
    assert injection_function < injection_stop < access_window

    # No qualification CLI may expose arbitrary RF/frame/count/retry knobs.
    assert source.count("ap.add_argument(") == 2
    assert 'ap.add_argument("--transmit"' in source
    assert 'ap.add_argument("--confirm"' in source
    for forbidden_option in (
        "--frequency",
        "--freq",
        "--power",
        "--payload",
        "--frame",
        "--source",
        "--destination",
        "--path",
        "--count",
        "--retry",
        "--txdelay",
        "--persist",
        "--slottime",
        "--port",
        "--host",
    ):
        assert forbidden_option not in source, forbidden_option

    for forbidden_mechanism in (
        ".transmit_selector_burst(",
        ".transact(",
        "rf_abort(",
        "rf_exit(",
        "stm32flash",
        "RPi.GPIO",
        "/sys/class/gpio",
        "gpiozero",
        "flash.sh",
        "restore-stock",
    ):
        assert forbidden_mechanism not in source, forbidden_mechanism

    # Host-qualified source boundaries remain byte-identical on the live branch.
    expected_blobs = {
        "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
        "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
        "src/ywd1278/kiss/tx_backend.py": "e06c1a619a02ecb4cf2073a3f270be1b2d54ea0e",
        "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
        "src/ywd1278/tx/contextual.py": "c9de1ed7e751d6d96eadc4f6ac7b027cfe859012",
        "src/ywd1278/tx/half_duplex.py": "d826fd4a53d52ba359eb0b45642370db0f0cb7cc",
        "src/ywd1278/tx/txdelay.py": "b8035a58c4b48765c580dab06bcdb054a9801c8c",
        "src/ywd1278/tx/access_queue.py": "d3631b549ea87cb14ce66e1020d74971c4c51392",
        "src/ywd1278/tx/broker.py": "1e3307dccea4f2805d32cb9be5b34f3537e29c4f",
    }
    for path, expected in expected_blobs.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    # Body/frame SHA fields in the manifest agree with the locked hex itself.
    body = bytes.fromhex(data["kiss_body_hex"])
    frame = bytes.fromhex(data["frame_with_fcs_hex"])
    assert hashlib.sha256(body).hexdigest() == data["kiss_body_sha256"]
    assert hashlib.sha256(frame).hexdigest() == data["frame_with_fcs_sha256"]
    assert frame[:-2] == body

    print("P7_LIVE_KISS_ONE_SHOT_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
