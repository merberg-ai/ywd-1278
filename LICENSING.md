# YWD-1278 Licensing and Source Lineage

YWD-1278 is a product repository assembled from two categories of work:

1. original YWD host-side software, tooling, documentation, configuration, and appliance integration;
2. firmware work derived from the upstream `MMDVM_HS` project.

## Project license policy

The intended distribution license for YWD-1278 is **GPL-2.0-or-later** so the complete product can be redistributed under one GPL-compatible umbrella while preserving upstream obligations.

The canonical license text will be added before the first distributable release. Until that file is present, this branch is development-only and should not be packaged as a release artifact.

## MMDVM_HS-derived firmware

The firmware lineage currently traces to:

- upstream project: `juribeparada/MMDVM_HS`
- qualified upstream commit used by the engineering reference: `7ff74ed1ba663a282edcbbb5e0ec3d7132e6f2f5`
- engineering/reference repository: `merberg-ai/ywd-mmdvm`
- frozen product-foundation checkpoint: `checkpoint/ax25-bidirectional-tnc-foundation`
- qualification evidence commit: `d25180ad663d781b761c525d1e699e7b052d6214`

Any source file copied from or derived from `MMDVM_HS` must retain its applicable upstream copyright/SPDX notices. YWD-1278 branding must never erase upstream attribution.

## YWD-MMDVM host-side reuse

Original YWD-MMDVM host-side scripts and documentation were released under The Unlicense unless an individual file states otherwise. Such material may be incorporated into YWD-1278 and distributed under GPL-2.0-or-later.

Every imported component should be recorded in `docs/development/porting-manifest.md` with its source path, source checkpoint/commit, destination path, and qualification status.

## Firmware binaries

Do not commit unknown/vendor stock firmware dumps to this repository unless redistribution rights are clear.

The stock-restore workflow should normally use a **local protected backup made from the user's own supported HAT before first YWD-1278 flash**, plus an optional separately distributed known-good stock image only when licensing/provenance permits it.
