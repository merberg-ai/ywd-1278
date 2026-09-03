#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
import qualify_live_p5_txdelay_ywdnod_r3 as r3  # noqa: E402

MANIFEST = ROOT / "firmware" / "qualification" / "0c-p5-live-txdelay-ywdnod.json"
R1 = ROOT / "tools" / "qualify_live_p5_txdelay_ywdnod.py"
R2 = ROOT / "tools" / "qualify_live_p5_txdelay_ywdnod_r2.py"
R3 = ROOT / "tools" / "qualify_live_p5_txdelay_ywdnod_r3.py"

m = json.loads(MANIFEST.read_text(encoding="utf-8"))
r1 = R1.read_text(encoding="utf-8")
r2 = R2.read_text(encoding="utf-8")
r3_text = R3.read_text(encoding="utf-8")

assert m["schema"] == 1
assert m["phase"] == "0C-P5-live"
assert m["attempt"] == "R3"
assert m["status"] == "staged"
assert m["base_checkpoint"] == "checkpoint/0c-p5-txdelay-host-qualified"
assert m["base_checkpoint_sha"] == "30cc677fbcc9fc9bab1aa1a18c18850ed1ef40a1"
assert m["authorized_harness"] == "tools/qualify_live_p5_txdelay_ywdnod_r3.py"
assert m["core_harness"] == "tools/qualify_live_p5_txdelay_ywdnod_r2.py"
assert m["superseded_unrun_harnesses"] == [
    "tools/qualify_live_p5_txdelay_ywdnod.py",
    "tools/qualify_live_p5_txdelay_ywdnod_r2.py",
]

# Fixed physical profile; no operator redirect knobs.
assert m["device"] == "/dev/ttyAMA0"
assert m["frequency_hz"] == 145050000
assert m["rf_power"] == 200
assert m["cycles"] == 2
assert m["source"] == "KJ6YWD-10"
assert m["destination"] == "YWD5TD"
assert m["digipeater_station"] == "KJ6YWD-5"
assert m["digipeater_alias"] == "YWDNOD"
assert m["path"] == ["YWDNOD"]
assert m["maximum_transmit_submissions"] == 2
assert m["automatic_tx_retry"] is False

# Exact two TXDELAY vectors.
expected = [
    {
        "cycle": 1,
        "txdelay_units": 30,
        "requested_txdelay_ms": 300,
        "pre_flags": 45,
        "information_text": "YWD-1278 P5 TXDELAY 300MS 1/2",
        "frame_bytes": 54,
        "frame_sha256": "d70b96a24f100e148008a495a808485e5bdc56bf7d408f15b73533e54ad46ee9",
        "selector_count": 817,
        "packed_selector_bytes": 103,
        "packed_selector_sha256": "534383e423bdf4f71cdafa3da9d1bbdb0bfc165e1a14d8fbd0fd676df15be145",
        "expected_generated_samples": 13072,
    },
    {
        "cycle": 2,
        "txdelay_units": 50,
        "requested_txdelay_ms": 500,
        "pre_flags": 75,
        "information_text": "YWD-1278 P5 TXDELAY 500MS 2/2",
        "frame_bytes": 54,
        "frame_sha256": "27cda8b62652f5bc855a75b0c41e0fe6b1168ee059be4a01c097f4bcef171253",
        "selector_count": 1057,
        "packed_selector_bytes": 133,
        "packed_selector_sha256": "f0c9b7c1e08fb9cf512fa6afa7d57b84e33f42af226e4d4957b00a6ca174cb22",
        "expected_generated_samples": 16912,
    },
]
assert len(m["frames"]) == 2
for actual, wanted in zip(m["frames"], expected):
    for key, value in wanted.items():
        assert actual[key] == value, (key, actual[key], value)

# The core must expose only the two physical CLI gates. Frequency, power,
# device, path, payload, count, and TXDELAY profiles cannot be operator-changed.
tree = ast.parse(r2)
long_options: set[str] = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
                    long_options.add(arg.value)
assert long_options == {"--transmit", "--confirm"}, long_options
for forbidden in (
    "--frequency",
    "--frequency-hz",
    "--power",
    "--device",
    "--path",
    "--payload",
    "--count",
    "--txdelay",
):
    assert forbidden not in long_options

# Default execution exits before TXModemOwner construction.
assert r2.index("if not args.transmit:") < r2.index("owner = TXModemOwner(")
assert "TX_MODEM_OWNER_CONSTRUCTED=NO" in r2
assert "HARDWARE_UART_OPENED=NO" in r2
assert "RF_TRANSMITTED=NO" in r2

# R3 owns the exact operator gate and semantic self-traffic classifier.
assert m["confirmation_token"] == r3.CONFIRMATION_TOKEN
assert m["interactive_phrase"] == r3.INTERACTIVE_CONFIRMATION
assert r3.CONFIRMATION_TOKEN == "P5-LIVE-YWDNOD-TXDELAY-30-50-R3"
assert r3.INTERACTIVE_CONFIRMATION == "TRANSMIT-P5-R3-TXDELAY-VIA-YWDNOD-TWO"
assert "r2.CONFIRMATION_TOKEN = CONFIRMATION_TOKEN" in r3_text
assert "r2.INTERACTIVE_CONFIRMATION = INTERACTIVE_CONFIRMATION" in r3_text
assert "r2.is_qualification_frame = semantic_qualification_frame" in r3_text

# Prove semantic classification catches both a direct frame and a real
# digipeated/H-bit variant, while not suppressing unrelated KJ6YWD traffic.
info = b"YWD-1278 P5 TXDELAY 300MS 1/2"
direct = build_ui_frame(
    source=Address.parse("KJ6YWD-10"),
    destination=Address.parse("YWD5TD"),
    path=(Address.parse("YWDNOD"),),
    info=info,
    include_fcs=True,
)
repeated = build_ui_frame(
    source=Address.parse("KJ6YWD-10"),
    destination=Address.parse("YWD5TD"),
    path=(Address.parse("YWDNOD", flag=True),),
    info=info,
    include_fcs=True,
)
unrelated = build_ui_frame(
    source=Address.parse("KJ6YWD"),
    destination=Address.parse("JIM"),
    info=b"trigger traffic",
    include_fcs=True,
)
assert direct != repeated
assert r3.semantic_qualification_frame(direct, {direct}) is True
assert r3.semantic_qualification_frame(repeated, {direct}) is True
assert r3.semantic_qualification_frame(unrelated, {direct}) is False
assert m["qualification_frames_may_authorize_later_tx"] is False
assert m["final_rx_proof_may_be_qualification_frame"] is False
assert m["qualification_frame_matching"].startswith("semantic-")
assert "QUALIFICATION_ECHO_IGNORED_AS_TRIGGER=YES" in r2
assert "FINAL_QUALIFICATION_ECHO_IGNORED_AS_RX_PROOF=YES" in r2

# Qualified channel-access / half-duplex graph remains mandatory.
for required in (
    "TXDelayBroker(",
    "PersistentHalfDuplexSubmitter(",
    "BoundedChannelAccessQueue(",
    "owner.rx_rssi(",
    "p4e_live.drain_rx(",
    "p4e_live.require_active_rx(",
    "random_byte_source=qualification_random_byte",
    "return 255",
    "return 0",
    "MIN_FULL_SLOT_SECONDS = 0.100",
):
    assert required in r2, required
assert m["requires_live_busy_before_each_tx"] is True
assert m["requires_fresh_fcs_valid_rx_trigger_before_each_tx"] is True
assert m["qualification_randomness"] == {
    "before_fresh_decoded_busy_trigger": 255,
    "after_fresh_decoded_busy_trigger": [255, 0],
}

# Failure accounting is exact per active cycle, not the R1 conservative
# double-count expression. Any accepted TX makes the full harness non-rerunnable.
assert "active_cycle_base = accepted_tx_count" in r2
assert "def exact_accepted_count()" in r2
assert "active_cycle_base + active_lifecycle.snapshot.downstream_accepted" in r2
assert "active_cycle_base + active_broker.snapshot.accepted" in r2
assert "accepted_tx_count + active_lifecycle.snapshot.downstream_accepted" not in r2
assert "accepted_tx_count + active_broker.snapshot.accepted" not in r2
assert "accepted_tx_count = exact_accepted_count()" in r2
assert "DO_NOT_RERUN_FULL_P5_R2_LIVE_HARNESS=YES" in r2
assert m["failure_accepted_tx_accounting"].startswith("exact-active-cycle-base")

# External qualification gate explicitly requires both direct and YWDNOD* copies.
assert m["requires_direct_external_decode_of_all_outgoing_frames"] is True
assert m["requires_ywdnod_repeated_decode_of_all_outgoing_frames"] is True
assert m["expected_repeated_path_marker"] == "YWDNOD*"
assert m["required_external_direct_decodes"] == 2
assert m["required_external_ywdnod_repeat_decodes"] == 2
assert "EXTERNAL_DIRECT_DECODE_REQUIRED=2" in r2
assert "EXTERNAL_YWDNOD_REPEAT_DECODE_REQUIRED=2" in r2
assert "QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DIRECT_AND_YWDNOD_REPEAT_DECODE" in r2

# No KISS/product TX or firmware-management side paths are introduced.
assert m["kiss_parameter_ingress_connected"] is False
assert m["kiss_data_tx_connected"] is False
assert m["product_tx_enabled"] is False
assert m["flash_permitted"] is False
assert m["gpio_reset_permitted"] is False
assert m["option_bytes_permitted"] is False
for forbidden in (
    "ywd1278.kiss",
    "stm32flash",
    "pinctrl",
    "subprocess",
    "os.system",
):
    assert forbidden not in r2
    assert forbidden not in r3_text

print("P5_LIVE_TXDELAY_YWDNOD_R3_CONTRACT=PASS")
print("P5_PHYSICAL_PATH=VIA_YWDNOD")
print("YWDNOD_STATION_ID=KJ6YWD-5")
print("TXDELAY_PROFILES=30,50")
print("SEMANTIC_SELF_REPEAT_TRIGGER_EXCLUSION=PASS")
print("EXACT_ACCEPTED_TX_FAILURE_ACCOUNTING=PASS")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
