#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.access_queue import BoundedChannelAccessQueue  # noqa: E402
from ywd1278.tx.channel_busy import (  # noqa: E402
    BUSY_ASSERT_RAW_MAX,
    CLEAR_RELEASE_RAW_MIN,
    RECENT_RX_HOLD_SECONDS,
)
from ywd1278.tx.csma import (  # noqa: E402
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_PERSIST,
    DEFAULT_SLOT_TIME_10MS,
)

SOURCE_PATH = ROOT / "src" / "ywd1278" / "tx" / "access_queue.py"
KISS_PATH = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON_PATH = ROOT / "src" / "ywd1278" / "daemon.py"
source = SOURCE_PATH.read_text(encoding="utf-8")
kiss = KISS_PATH.read_text(encoding="utf-8")
daemon = DAEMON_PATH.read_text(encoding="utf-8")
tree = ast.parse(source)

# Qualified P1/P2 policy values remain unchanged at the P4a composition layer.
assert BUSY_ASSERT_RAW_MAX == 83
assert CLEAR_RELEASE_RAW_MIN == 90
assert RECENT_RX_HOLD_SECONDS == 0.250
assert DEFAULT_PERSIST == 63
assert DEFAULT_SLOT_TIME_10MS == 10
assert DEFAULT_MAX_WAIT_SECONDS == 30.0

# Constructor defaults define one finite host queue and one finite total request
# lifetime. The scheduler itself remains synchronous/deterministic.
class Sink:
    def submit_frame(self, frame_with_fcs: bytes, *, timeout: float | None = None) -> object:
        raise AssertionError("contract construction must not submit")

scheduler = BoundedChannelAccessQueue(Sink())
snap = scheduler.snapshot
assert snap.queue_capacity == 4
assert snap.queue_depth == 0
assert snap.active_request_id is None

# Inspect imports structurally so English comments mentioning the real broker do
# not create false positives. P4a may import only protocol/pure state helpers.
imports: list[tuple[int, str]] = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.extend((0, alias.name) for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        imports.append((node.level, node.module or ""))

for level, module in imports:
    assert module not in {
        "threading",
        "time",
        "random",
        "secrets",
        "socket",
        "socketserver",
        "subprocess",
        "queue",
    }, (level, module)
    assert not module.startswith("ywd1278.modem"), (level, module)
    assert not module.startswith("ywd1278.kiss"), (level, module)
    assert not (level == 1 and module == "broker"), (level, module)

# Required architecture and fail-closed semantics are explicit in source.
for required in (
    "class FrameSubmitter(Protocol)",
    "class BoundedChannelAccessQueue",
    "verify_fcs(frame)",
    "len(self._queue) >= self._queue_capacity",
    "deadline_at=now + self._request_timeout_seconds",
    "remaining = request.receipt.deadline_at - now",
    "ShadowChannelAccessAttempt",
    "CSMAState.READY",
    "self._submitter.submit_frame",
    "self._queue.popleft()",
    "downstream_timeout_seconds",
    "downstream submission",
    "does not import or construct the real TX broker",
):
    assert required in source, required

# Ordinary KISS and daemon paths remain TX-disconnected. P4a is not reachable
# from product network input and cannot create a transmit-capable object.
for forbidden in (
    "BoundedChannelAccessQueue",
    "FrameSubmitter",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("P4A_ACCESS_QUEUE_CONTRACT=PASS")
print("QUEUE_CAPACITY_DEFAULT=4")
print("TOTAL_REQUEST_LIFETIME_SECONDS=30.0")
print("PERSIST=63")
print("SLOTTIME_10MS=10")
print("P2_BUSY_ASSERT_RAW_MAX=83")
print("P2_CLEAR_RELEASE_RAW_MIN=90")
print("REAL_TX_BROKER_IMPORTED=NO")
print("TX_MODEM_OWNER_IMPORTED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("HARDWARE_ACCESS=NO")
print("RF_TRANSMITTED=NO")
