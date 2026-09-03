#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path],
        cwd=ROOT,
        text=True,
    ).strip()


# Frozen qualified components must not be edited by P7.
assert git_blob("src/ywd1278/tx/access_queue.py") == "d3631b549ea87cb14ce66e1020d74971c4c51392"
assert git_blob("src/ywd1278/tx/half_duplex.py") == "d826fd4a53d52ba359eb0b45642370db0f0cb7cc"
assert git_blob("src/ywd1278/tx/txdelay.py") == "b8035a58c4b48765c580dab06bcdb054a9801c8c"
assert git_blob("src/ywd1278/tx/broker.py") == "1e3307dccea4f2805d32cb9be5b34f3537e29c4f"

admission = text("src/ywd1278/kiss/tx_path.py")
backend = text("src/ywd1278/kiss/tx_backend.py")
contextual = text("src/ywd1278/tx/contextual.py")

# KISS DATA is an AX.25 body without FCS.  The TNC validates the body and
# appends FCS exactly once before the qualified TX graph.
assert "parse_frame(frame_no_fcs, has_fcs=False)" in admission
assert "frame_with_fcs = append_fcs(frame_no_fcs)" in admission
assert "verify_fcs" not in backend

# Immutable P6 context travels with the request and controls both CSMA and
# TXDELAY.  The queue must not read live session state after admission.
assert "context: TNCTransmitContext" in admission
assert "captured = request.context.csma_parameters" in admission
assert "persist=captured.persist" in admission
assert "slot_time_10ms=captured.slot_time_10ms" in admission
assert "self._submitter.submit_frame(" in admission
assert "request.context" in admission
assert "self.session.capture_tx_context" in backend

# No same-request requeue or retry helper exists.  Safety documentation is
# allowed to contain the words "no automatic retry".
assert ".appendleft(" not in admission
assert "def retry" not in admission
assert "is terminal and is not retried" in admission

# P7 backend can admit DATA but cannot advance channel access by itself.
assert "def observe_rssi" not in backend
assert "KISSDataAdmissionQueue" in backend

# Explicit construction-time TX authority remains fail-closed.  P7 reuses the
# qualified P5 broker and exact P4e lifecycle rather than implementing either.
assert "transmit_enabled: bool = False" in contextual
assert "TXDelayBroker(" in contextual
assert "PersistentHalfDuplexSubmitter(" in contextual
assert "frame_to_selectors" not in contextual
assert "transmit_selector_burst" not in contextual
assert "rx_stop(" not in contextual
assert "rx_start(" not in contextual

# Production-hardware mechanisms remain absent from all new P7 modules.
for source in (admission, backend, contextual):
    lower = source.lower()
    assert "serialtransport" not in lower
    assert "posixserial" not in lower
    assert "stm32flash" not in lower
    assert "option byte" not in lower
    assert "gpiod" not in lower
    assert "gpiozero" not in lower
    assert "rpi.gpio" not in lower
    assert "/dev/tty" not in lower

manifest = json.loads(text("firmware/qualification/0c-p7-kiss-data-admission.json"))
assert manifest["phase"] == "0C-P7"
assert manifest["base_checkpoint_sha"] == "860104a7dbaff3dac642b72cc040d746375e7264"
assert manifest["kiss_data"]["payload_has_fcs"] is False
assert manifest["kiss_data"]["tnc_appends_fcs_exactly_once"] is True
assert manifest["request_policy"]["per_request_parameter_snapshot"] is True
assert manifest["request_policy"]["automatic_retry"] is False
assert manifest["safety"]["host_fake_modem_only"] is True
assert manifest["safety"]["posix_serial"] is False
assert manifest["safety"]["uart_access"] is False
assert manifest["safety"]["rf_transmitted"] is False
assert manifest["safety"]["product_tx_enabled"] is False
assert manifest["physical_follow_on"]["require_path"] == ["YWDNOD"]
assert manifest["physical_follow_on"]["require_ywdnod_repeated_decode"] is False
assert manifest["physical_follow_on"]["authorized"] is False

print("P7_KISS_DATA_ARCHITECTURE_CONTRACT=PASS")
print("P4A_FROZEN=PASS")
print("P4E_FROZEN=PASS")
print("P5_TXDELAY_FROZEN=PASS")
print("TX_BROKER_FROZEN=PASS")
print("KISS_DATA_FCS_OWNERSHIP=TNC")
print("PER_REQUEST_CONTEXT=IMMUTABLE")
print("AUTOMATIC_RETRY=NO")
print("PHYSICAL_P7_AUTHORIZED=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("RF_TRANSMITTED=NO")
