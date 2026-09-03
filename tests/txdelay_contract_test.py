#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx import KISS_TXDELAY_DEFAULT, TXBroker, TXDelayBroker, resolve_txdelay  # noqa: E402

MANIFEST = ROOT / "firmware" / "qualification" / "0c-p5-txdelay-host.json"
BROKER = ROOT / "src" / "ywd1278" / "tx" / "broker.py"
TXDELAY = ROOT / "src" / "ywd1278" / "tx" / "txdelay.py"
KISS_SERVER = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
broker_bytes = BROKER.read_bytes()
txdelay_text = TXDELAY.read_text(encoding="utf-8")
kiss_text = KISS_SERVER.read_text(encoding="utf-8")
daemon_text = DAEMON.read_text(encoding="utf-8")

# The previously physically qualified P4e boundary is the exact base.
assert manifest["phase"] == "0C-P5"
assert manifest["stage"] == "txdelay-host-policy"
assert manifest["status"] == "host-qualified"
assert manifest["base_checkpoint_sha"] == "b6b18631e9e1abaa2854f1a69a7a4dc56d08e71d"
host = manifest["host_qualification"]
assert host["p5_ci_run_id"] == 33713270977
assert host["p5_ci_conclusion"] == "success"
assert host["framework_ci_run_id"] == 33713284950
assert host["framework_ci_run_number"] == 393
assert host["framework_ci_conclusion"] == "success"
assert host["default_p5_vector_preserved"] is True
assert host["historical_broker_blob_preserved"] is True

# Historical P13/P4 broker implementation is byte-for-byte untouched. P5 is a
# later subclass boundary rather than a rewrite of frozen serializer evidence.
blob_sha1 = hashlib.sha1(f"blob {len(broker_bytes)}\0".encode() + broker_bytes).hexdigest()
assert blob_sha1 == manifest["historical_tx_broker_git_blob_sha1"]
assert blob_sha1 == "1e3307dccea4f2805d32cb9be5b34f3537e29c4f"
assert issubclass(TXDelayBroker, TXBroker)
assert "class TXDelayBroker(TXBroker)" in txdelay_text
assert "def _prepare_frame" in txdelay_text
assert "pre_flags=self._txdelay_profile.pre_flags" in txdelay_text
assert "P5_POST_FLAGS" in txdelay_text
assert "P5_INITIAL_TONE" in txdelay_text
assert "selector_count > protocol.MAX_SELECTORS" in txdelay_text

# KISS-byte semantics and the frozen default are exact.
assert KISS_TXDELAY_DEFAULT == 30
assert resolve_txdelay(30).pre_flags == 45
assert resolve_txdelay(30).effective_seconds == 0.3
assert resolve_txdelay(50).pre_flags == 75
assert resolve_txdelay(50).effective_seconds == 0.5
assert manifest["parameter_min"] == 0
assert manifest["parameter_max"] == 255
assert manifest["default"] == 30
assert manifest["runtime_mutation"] is False
assert "def set_txdelay" not in txdelay_text
assert "set_txdelay(" not in txdelay_text

# This phase owns no hardware, timing loop, randomness, sockets, or KISS
# ingress. TXDelayBroker only changes deterministic frame preparation.
for forbidden in (
    "/dev/tty",
    "posix_serial_transport_factory",
    "pinctrl",
    "stm32flash",
    "import socket",
    "import random",
    "import time",
    "ywd1278.kiss",
):
    assert forbidden not in txdelay_text, forbidden
assert manifest["hardware_access"] is False
assert manifest["rf_transmitted"] is False
assert manifest["kiss_parameter_ingress_connected"] is False
assert manifest["kiss_data_tx_connected"] is False
assert manifest["product_tx_enabled"] is False

# Existing KISS/product path remains RX-only during TXDELAY qualification.
for forbidden in ("TXDelayBroker", "set_txdelay", "KISS_TXDELAY"):
    assert forbidden not in kiss_text, forbidden
    assert forbidden not in daemon_text, forbidden

# Any physical TX follow-on for this phase is locked to the user's requested
# YWDNOD digipeater alias, whose station identity is KJ6YWD-5.
physical = manifest["physical_follow_on"]
assert physical["frequency_hz"] == 145050000
assert physical["rf_power"] == 200
assert physical["digipeater_station"] == "KJ6YWD-5"
assert physical["digipeater_alias_path"] == "YWDNOD"
assert physical["require_path"] == ["YWDNOD"]
assert physical["txdelay_profiles"] == [30, 50]
assert physical["requested_ms"] == [300, 500]
assert physical["require_direct_external_decode"] is True
assert physical["require_ywdnod_repeated_decode"] is True
assert physical["expected_repeated_path_marker"] == "YWDNOD*"
assert physical["automatic_tx_retry"] is False
assert physical["kiss_tx_connected"] is False

print("P5_TXDELAY_ARCHITECTURE_CONTRACT=PASS")
print("P5_TXDELAY_HOST_STATUS=QUALIFIED")
print("HISTORICAL_TX_BROKER_BLOB_FROZEN=PASS")
print("TXDELAY_DEFAULT_30_EQUALS_P5_45_FLAGS=PASS")
print("RUNTIME_TXDELAY_MUTATION=NO")
print("KISS_PARAMETER_INGRESS=DISCONNECTED")
print("KISS_DATA_TX=DISCONNECTED")
print("P5_PHYSICAL_PATH=VIA_YWDNOD")
print("YWDNOD_STATION_ID=KJ6YWD-5")
print("RF_TRANSMITTED_BY_CI=NO")
