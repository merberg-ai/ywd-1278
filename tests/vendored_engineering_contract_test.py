#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P10 = ROOT / "firmware/tooling/packet-build-manifest.json"
P2 = ROOT / "firmware/tooling/packet-rssi-build-manifest.json"
MATERIALIZER = ROOT / "firmware/tooling/materialize_vendored_engineering.py"
P10_BUILDER = ROOT / "firmware/build-packet-ywd1278.sh"
P2_BUILDER = ROOT / "firmware/build-packet-rssi-ywd1278.py"
WRAPPER = ROOT / "firmware/build-packet-ywd1278-frozen.sh"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


p10 = load(P10)
p2 = load(P2)
for manifest in (p10, p2):
    eng = manifest["engineering"]
    assert eng["source"] == "vendored"
    assert eng["vendored_root"] == "firmware/vendor/ywd-mmdvm"
    root = ROOT / eng["vendored_root"]
    assert root.is_dir()
    for rel, expected in eng["files"].items():
        path = root / rel
        assert path.is_file(), rel
        actual = git_blob_sha1(path.read_bytes())
        assert actual == expected, f"{rel}: expected={expected} actual={actual}"

assert len(p10["engineering"]["files"]) == 12
assert len(p2["engineering"]["files"]) == 13
assert p10["engineering"]["commit"] == "d25180ad663d781b761c525d1e699e7b052d6214"
assert p2["engineering"]["baseline_qualified_commit"] == p10["engineering"]["commit"]
assert p2["engineering"]["commit"] == "69309644da839522102e393e66093378544869ea"
for rel, sha in p10["engineering"]["files"].items():
    assert p2["engineering"]["files"][rel] == sha
assert p2["engineering"]["files"]["firmware/ax25-rx4/apply_ax25_rx4_rssi.py"] == (
    "f69382dc0dbdb5c9d04bf2b04ea197d2840e5e03"
)

materializer = MATERIALIZER.read_text(encoding="utf-8")
p10_builder = P10_BUILDER.read_text(encoding="utf-8")
p2_builder = P2_BUILDER.read_text(encoding="utf-8")
wrapper = WRAPPER.read_text(encoding="utf-8")

for text in (p10_builder, p2_builder, wrapper):
    for forbidden in (
        "--engineering-repo",
        "YWD1278_ENGINEERING_REPO",
        "mmdvm-lab/ywd-mmdvm",
    ):
        assert forbidden not in text, forbidden

for required in (
    "VENDORED_ENGINEERING_BLOBS=PASS",
    "ENGINEERING_EXTERNAL_REPO_REQUIRED=NO",
    "ENGINEERING_NETWORK_FETCH_REQUIRED=NO",
):
    assert required in materializer, required

for forbidden in ("git fetch", "git clone", "subprocess.check_output([\"git\""):
    assert forbidden not in materializer, forbidden

print("VENDORED_ENGINEERING_CONTRACT=PASS")
print("P10_VENDORED_BLOBS=12")
print("P2_VENDORED_BLOBS=13")
print("ORIGINAL_GIT_BLOB_IDENTITIES=PASS")
print("ENGINEERING_EXTERNAL_REPO_REQUIRED=NO")
print("ENGINEERING_NETWORK_FETCH_REQUIRED=NO")
print("YWD1278_SELF_CONTAINED_ENGINEERING=PASS")
