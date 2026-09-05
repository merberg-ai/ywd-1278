#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import threading
import tomllib

from ywd1278.ax25 import Address, build_ui_frame, parse_frame
from ywd1278.kiss.framing import DATA, encode

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage_i", ROOT / "tools/qualify_stage_i_single_tx.py"
)
assert SPEC and SPEC.loader
stage_i = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage_i)


def example_config() -> str:
    return '''[station]\ncallsign = "KJ6YWD"\nssid = 10\n\n[hardware]\ntarget = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"\n\n[radio]\ndevice = "/dev/ttyAMA0"\nfrequency_mhz = 145.050\ntx_power = 64\ntx_enabled = false\n\n[packet]\nbaud = 1200\ntxdelay_ms = 300\npersist = 63\nslottime_ms = 100\npaclen = 128\nmaxframe = 4\nretry = 10\n\n[kiss]\nenabled = true\nlisten = "127.0.0.1"\nport = 8001\n\n[console]\nenabled = true\nlisten = "127.0.0.1"\nport = 8010\npty_enabled = true\npty_link = "/run/ywd-1278/tnc"\n\n[monitor]\nenabled = true\nlog_frames = true\n\n[storage]\ndatabase = "/var/lib/ywd-1278/ywd-1278.sqlite3"\n\n[beacon]\nenabled = false\ninterval_seconds = 600\ndestination = "BEACON"\npath = []\ntext = "YWD-1278 packet node"\n\n[firmware]\nrequired_product = "YWD-1278"\nallow_automatic_flash = false\n'''


def status(*, tx: int, accepted: int, dispatched: int, depth: int, received: int, admitted: int) -> str:
    return "\n".join(
        [
            "STATUS OK",
            f"RUNTIME access_timeouts=0 decoded_rx_frames=1 decoder_resets_after_tx={tx} failure=- identity=x packed_rx_bytes=1 rssi_samples=1 running=true rx_read_transactions=1 rx_status_checks=1 tx_dispatches={tx}",
            "BACKEND client_messages_rejected=0 events_published=1 history_depth=1 subscriber_drops=0 subscribers=0",
            f"INGRESS data_admitted={admitted} data_invalid_rejections=0 data_messages_received={received} data_other_rejections=0 data_queue_full_drops=0 data_time_rejections=0",
            f"QUEUE tx_access_timeouts=0 tx_dispatched={dispatched} tx_downstream_failures=0 tx_invalid_rejections=0 tx_queue_accepted={accepted} tx_queue_capacity=8 tx_queue_depth={depth} tx_queue_full_drops=0",
        ]
    )


def test_fixed_vector_is_direct_ui_without_fcs() -> None:
    body = stage_i.build_vector()
    parsed = parse_frame(body, has_fcs=False)
    assert str(parsed["source"]) == "KJ6YWD-10"
    assert str(parsed["destination"]) == "YWD127"
    assert parsed["path"] == []
    assert parsed["info"] == b"YWD-1278 STAGE-I TX 1/1"
    assert stage_i.expected_external_decode() == "KJ6YWD-10>YWD127:YWD-1278 STAGE-I TX 1/1"


def test_temp_tx_config_changes_only_bounded_runtime_fields() -> None:
    original = example_config()
    modified = stage_i.make_temporary_tx_config(original)
    before = tomllib.loads(original)
    after = tomllib.loads(modified)
    assert before["radio"]["tx_enabled"] is False
    assert before["radio"]["tx_power"] == 64
    assert after["radio"]["tx_enabled"] is True
    assert after["radio"]["tx_power"] == 200
    assert after["kiss"]["port"] == 18001
    assert after["console"]["port"] == 18010
    assert after["console"]["pty_link"] == "/run/ywd-1278/stage-i-tnc"
    assert after["radio"]["frequency_mhz"] == before["radio"]["frequency_mhz"]
    assert after["radio"]["device"] == before["radio"]["device"]
    assert after["firmware"] == before["firmware"]
    assert after["beacon"] == before["beacon"]
    assert after["station"] == before["station"]


def test_persistent_config_validator_requires_safe_stage_h_state() -> None:
    root = tomllib.loads(example_config())
    assert stage_i.validate_persistent_config(root) == "KJ6YWD-10"
    root["radio"]["tx_enabled"] = True
    try:
        stage_i.validate_persistent_config(root)
    except ValueError as exc:
        assert "persistent TX" in str(exc)
    else:
        raise AssertionError("persistent tx_enabled=true was accepted")


def test_single_shot_status_accepts_exactly_one_and_rejects_duplicate() -> None:
    stage_i.assert_single_shot_status(
        status(tx=0, accepted=0, dispatched=0, depth=0, received=0, admitted=0),
        require_dispatched=False,
    )
    stage_i.assert_single_shot_status(
        status(tx=1, accepted=1, dispatched=1, depth=0, received=1, admitted=1),
        require_dispatched=True,
    )
    try:
        stage_i.assert_single_shot_status(
            status(tx=2, accepted=1, dispatched=2, depth=0, received=1, admitted=1),
            require_dispatched=True,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("duplicate dispatch accounting was accepted")


def test_post_tx_rx_filter_ignores_exact_qualification_echo() -> None:
    left, right = socket.socketpair()
    try:
        tx = stage_i.build_vector()
        later = build_ui_frame(
            source=Address.parse("KJ6YWD-5"),
            destination=Address.parse("YWD127"),
            path=[],
            info=b"POST TX RX PROOF",
            include_fcs=False,
        )

        def writer() -> None:
            right.sendall(encode(tx, command=DATA))
            right.sendall(encode(later, command=DATA))

        thread = threading.Thread(target=writer)
        thread.start()
        frame, source = stage_i.recv_post_tx_non_qualification(
            left, tx_source="KJ6YWD-10", timeout=2.0
        )
        thread.join(2.0)
        assert source == "KJ6YWD-5"
        assert frame == later
    finally:
        left.close()
        right.close()


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"STAGE_I_SINGLE_TX_REGRESSION=PASS tests={len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
