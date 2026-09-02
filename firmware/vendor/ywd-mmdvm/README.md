# Vendored YWD-MMDVM engineering lineage

YWD-1278 is a standalone project. Firmware builds do **not** require a local
checkout of `merberg-ai/ywd-mmdvm`.

This directory contains byte-for-byte copies of the small set of engineering
files that were originally developed and physically qualified in YWD-MMDVM.
Their original repository, commit IDs, and Git blob SHAs remain pinned in the
YWD-1278 firmware build manifests for provenance.

Before every firmware build, `firmware/tooling/materialize_vendored_engineering.py`
recomputes the Git blob SHA-1 for each vendored file and refuses to continue if
any byte differs from the manifest pin. The verified copies are then used to
reconstruct the packet firmware from the separately pinned upstream MMDVM_HS
source.

Historical provenance:

- AX25R3 qualified baseline: `merberg-ai/ywd-mmdvm` commit
  `d25180ad663d781b761c525d1e699e7b052d6214`
- AX25R4 read-only RSSI transform: `merberg-ai/ywd-mmdvm` commit
  `69309644da839522102e393e66093378544869ea`
- Upstream MMDVM_HS base remains separately pinned at
  `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`.

Vendoring changes acquisition only. It does not change the already-qualified
packet algorithms, RF behavior, clocks, transforms, or artifact provenance.
