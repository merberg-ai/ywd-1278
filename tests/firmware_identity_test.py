#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "firmware" / "probe_hat.py"
TARGETS = ROOT / "firmware" / "targets.json"

spec = importlib.util.spec_from_file_location("ywd1278_probe_hat", PROBE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
assert len(targets) >= 1
reference = targets[0]

stock = reference["stock_identities"][0]
matches, cls = module.classify_identity(stock, targets)
assert cls == "STOCK"
assert len(matches) == 1 and matches[0]["id"] == reference["id"]

engineering = reference["engineering_identities"][0]
matches, cls = module.classify_identity(engineering, targets)
assert cls == "YWD_ENGINEERING"
assert len(matches) == 1

ywd1278 = reference["ywd1278_identity_prefix"] + "v0.1.0 test identity"
matches, cls = module.classify_identity(ywd1278, targets)
assert cls == "YWD1278"
assert len(matches) == 1

unknown = "MMDVM_HS_Hat-v9.9.9 UNKNOWN VENDOR BUILD"
matches, cls = module.classify_identity(unknown, targets)
assert cls == "UNKNOWN"
assert matches == []

print("FIRMWARE_IDENTITY_CLASSIFICATION=PASS")
