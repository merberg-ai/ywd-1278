#!/usr/bin/env python3
"""Static and manifest contract for guarded 0C-P8 live sustained KISS qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "qualify_live_p8_sustained_kiss_tnc.py"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-live-sustained-kiss-tnc.json"


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
    assert data["phase"] == "0C-P8-live"
    assert data["stage"] == "sustained-kiss-three-cycle"
    assert data["status"] == "staged"
    assert data["base_checkpoint"] == "checkpoint/0c-p8-sustained-kiss-tnc-host-qualified"
    assert data["base_checkpoint_sha"] == "a835d2500dbdb4a8eaf1ae3cae4ea662203a852a"
    assert data["device"] == "/dev/ttyAMA0"
    assert data["frequency_hz"] == 145050000
    assert data["rf_power"] == 200
    assert data["packet_count"] == 3
    assert data["source"] == "KJ6YWD-10"
    assert data["destination"] == "YWD8"
    assert data["path"] == ["YWDNOD"]

    assert data["kiss_listener_host"] == "127.0.0.1"
    assert data["kiss_listener_port"] == 0
    assert data["kiss_listener_ephemeral"] is True
    assert data["kiss_client_sessions_required"] == 2
    assert data["kiss_client_reconnect_required"] is True
    assert data["kiss_data_payload_includes_fcs"] is False
    assert data["tnc_appends_fcs_exactly_once"] is True
    assert data["kiss_port"] == 0
    assert data["parameter_generations"] == [3, 4, 5]
    assert data["persist"] == 63
    assert data["slottime"] == 10
    assert data["fullduplex"] == 0
    assert data["txdelay_sequence"] == [30, 50, 30]

    assert data["request_timeout_seconds"] == 30.0
    assert data["downstream_timeout_seconds"] == 1.5
    assert data["rssi_poll_nominal_seconds"] == 0.05
    assert data["rx_status_interval_seconds"] == 0.25
    assert data["rx_read_maximum"] == 200
    assert data["busy_assert_raw_maximum"] == 83
    assert data["clear_release_raw_minimum"] == 90
    assert data["recent_rx_hold_seconds"] == 0.25
    assert data["requires_live_busy_before_each_dispatch"] is True
    assert data["requires_fresh_non_qualification_fcs_valid_rx_before_each_tx"] is True
    assert data["qualification_randomness"] == {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }
    assert data["minimum_full_slot_seconds"] == 0.1
    assert data["requires_rx_fifo_drained_before_tx_access"] is True
    assert data["requires_rx_active_after_each_tx"] is True
    assert data["rx_fifo_dropped_bytes_required"] == 0
    assert data["requires_final_queue_empty_fcs_valid_rx"] is True
    assert data["requires_final_queue_empty_kiss_delivery"] is True
    assert data["final_receive_timeout_seconds"] == 60.0
    assert data["required_non_qualification_inbound_frames"] == 4
    assert data["qualification_echo_must_not_count_as_rx_proof"] is True
    assert data["maximum_transmit_submissions"] == 3
    assert data["automatic_tx_retry"] is False
    assert data["requires_direct_external_decode"] is True
    assert data["required_external_tx_decodes"] == 3
    assert data["require_ywdnod_repeated_decode"] is False
    assert data["confirmation_token"] == "P8-LIVE-145050-P200-SUSTAINED-3"
    assert data["interactive_phrase"] == "TRANSMIT-P8-SUSTAINED-KISS-THREE"
    assert data["product_tx_enabled"] is False
    assert data["daemon_tx_enabled"] is False
    assert data["systemd_tx_enabled"] is False
    assert data["flash_permitted"] is False
    assert data["gpio_reset_permitted"] is False
    assert data["option_bytes_permitted"] is False

    frames = data["frames"]
    assert len(frames) == 3
    expected = [
        {
            "index": 1,
            "information_text": "YWD-1278 P8 SUSTAINED 1/3",
            "txdelay": 30,
            "pre_flags": 45,
            "post_flags": 3,
            "kiss_body_sha256": "e39be1909cd9a23a88f17b8f9447b0c523f07b2b38e88562899bcc654e362298",
            "frame_with_fcs_sha256": "8b1584d090515a5606ebe843dd31eabb331c18bd25ed8b39926c8077a4322664",
            "selector_count": 785,
            "packed_selector_bytes": 99,
            "packed_selector_sha256": "30ec41f88cd6dcf74be3d7f2d5b89fc17ddf3b0f173322000a43a7b4b8603543",
            "expected_generated_samples": 12560,
        },
        {
            "index": 2,
            "information_text": "YWD-1278 P8 SUSTAINED 2/3",
            "txdelay": 50,
            "pre_flags": 75,
            "post_flags": 3,
            "kiss_body_sha256": "b7d0305141ad1f6b3cef5907e349fc257a70b09015338e1d28f62b4439580987",
            "frame_with_fcs_sha256": "c618572c2f0d2642d08c0ffdb27be3231d37080da1172ca8b6b3529f4282122c",
            "selector_count": 1025,
            "packed_selector_bytes": 129,
            "packed_selector_sha256": "fded1c576224fd20cabc65192a1bccbe2c93108a85a7914f3105d65cb44a8f6f",
            "expected_generated_samples": 16400,
        },
        {
            "index": 3,
            "information_text": "YWD-1278 P8 SUSTAINED 3/3",
            "txdelay": 30,
            "pre_flags": 45,
            "post_flags": 3,
            "kiss_body_sha256": "ea2f51f1e6930c22830eacf21a7eeb10d1b5cf66c8582565bbc9988eb9ef0e33",
            "frame_with_fcs_sha256": "ff09d7a6683f3a827c7ee7d18f48f0ca0635f9379b354057df2b7bdb122f56db",
            "selector_count": 785,
            "packed_selector_bytes": 99,
            "packed_selector_sha256": "941b11b95e642e3d345e9f2dbf6824f79562507923de68e256f04394892535f5",
            "expected_generated_samples": 12560,
        },
    ]
    for locked, wanted in zip(frames, expected, strict=True):
        for key, value in wanted.items():
            assert locked[key] == value, (key, value, locked[key])
        assert locked["kiss_body_bytes"] == 48
        assert locked["frame_with_fcs_bytes"] == 50
        assert locked["samples_per_selector"] == 16
        body = bytes.fromhex(locked["kiss_body_hex"])
        frame = bytes.fromhex(locked["frame_with_fcs_hex"])
        assert len(body) == locked["kiss_body_bytes"]
        assert len(frame) == locked["frame_with_fcs_bytes"]
        assert frame[:-2] == body
        assert hashlib.sha256(body).hexdigest() == locked["kiss_body_sha256"]
        assert hashlib.sha256(frame).hexdigest() == locked["frame_with_fcs_sha256"]

    # Live staging must compose the host-qualified sustained path rather than
    # reconstructing or bypassing it with a qualification-only TX mechanism.
    for required in (
        "SustainedTNCBackend",
        "ThreadSafeKISSDataAdmissionQueue",
        "SustainedTNCRuntime",
        "TNCSessionState",
        "ContextualHalfDuplexSubmitter",
        "ContextualTXDelayRouter",
        "TXModemOwner",
        "posix_serial_transport_factory",
        "start_server_thread",
        "stop_server_thread",
        "guard.arm(1)",
        "guard.arm(2)",
        "guard.arm(3)",
        "CYCLE[1]_WINDOW=OPEN",
        "CYCLE[2]_WINDOW=OPEN",
        "CYCLE[3]_WINDOW=OPEN",
        "FINAL_QUEUE_EMPTY_RX_WINDOW=OPEN",
        "DO_NOT_RERUN_FULL_P8_LIVE_HARNESS=YES",
        "RF_TRANSMITTED=YES_EXACTLY_THREE_FIXED_BURSTS",
        "QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DECODE",
    ):
        assert required in source, required

    # Dry-run must return before modem owner construction, KISS listener creation,
    # UART access, or any RF-capable path can be opened.
    dry_run_marker = source.index("if not args.transmit:")
    owner_construct = source.index("owner = TXModemOwner(")
    listener_call = source.index("server, server_thread = start_server_thread(")
    assert dry_run_marker < owner_construct < listener_call
    dry = source[dry_run_marker:owner_construct]
    assert "P8_LIVE_SUSTAINED_KISS_DRY_RUN=PASS" in dry
    assert "TX_MODEM_OWNER_CONSTRUCTED=NO" in dry
    assert "KISS_LISTENER_OPENED=NO" in dry
    assert "HARDWARE_UART_OPENED=NO" in dry
    assert "RF_TRANSMITTED=NO" in dry

    # Two independent confirmations are required before owner construction.
    token_check = source.index("if args.confirm != CONFIRMATION_TOKEN:")
    uart_check = source.index("if not p4d_r1.uart_is_free():")
    interactive = source.index("typed = input(")
    interactive_check = source.index("if typed != INTERACTIVE_CONFIRMATION:")
    assert dry_run_marker < token_check < uart_check < interactive < interactive_check < owner_construct

    # Qualification CLI exposes no arbitrary RF/frame/count/retry controls.
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

    # No direct raw modem TX, raw transact, flash, reset, or option-byte escape hatch.
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

    # Host-qualified P8/P7/P6/P4e/P5 and modem/PHY source boundaries are frozen.
    expected_blobs = {
        "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
        "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
        "src/ywd1278/kiss/sustained.py": "63cf33f4b6d4cedd091af0349a8037669d45e84d",
        "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
        "src/ywd1278/service/tnc_runtime.py": "39c3b4c162e3e91b18f60fbca45f1a9d5ae12363",
        "src/ywd1278/tx/access_queue.py": "d3631b549ea87cb14ce66e1020d74971c4c51392",
        "src/ywd1278/tx/broker.py": "1e3307dccea4f2805d32cb9be5b34f3537e29c4f",
        "src/ywd1278/tx/channel_busy.py": "46c655a6d9143ac9ea21cbccb36caf77c4a14cd8",
        "src/ywd1278/tx/contextual.py": "c9de1ed7e751d6d96eadc4f6ac7b027cfe859012",
        "src/ywd1278/tx/csma.py": "b21925be0799d6d6ee887ba6dbb494014d50c710",
        "src/ywd1278/tx/half_duplex.py": "d826fd4a53d52ba359eb0b45642370db0f0cb7cc",
        "src/ywd1278/tx/txdelay.py": "b8035a58c4b48765c580dab06bcdb054a9801c8c",
        "src/ywd1278/modem/_serial.py": "c671633a9c0934cbc8206957eafc1d5736537fc7",
        "src/ywd1278/modem/tx_owner.py": "d32763473a1eba89566ed512e9ab5fc7de575480",
        "src/ywd1278/phy/bell202_rx.py": "18fae685a0accdeb2eb425793632cf123f45bbda",
        "src/ywd1278/phy/bell202_tx.py": "39677faa3302a74da9fbae6fa858899e54f1874f",
    }
    for path, expected_blob in expected_blobs.items():
        actual = git_blob(path)
        assert actual == expected_blob, (path, expected_blob, actual)

    print("P8_LIVE_SUSTAINED_KISS_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
