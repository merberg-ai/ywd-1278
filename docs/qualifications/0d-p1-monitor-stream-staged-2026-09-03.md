# 0D-P1 decoded monitor stream — staged

Base: `checkpoint/0c-complete-p8-physical-qualified` / `fc70386a3857e69437641d1be6f9f8cd0a6e7a13`

Development branch: `dev-0d-p1-monitor-stream`

This stage adds a read-only decoded monitor subscriber above the frozen 0C PacketEvent boundary.  No 0C/P8 core source is changed.

Host qualification must prove:

- bounded backend history is emitted before live records in source order;
- UI, physical I-frame and supervisory frame examples become structured records;
- repeated path H bits display as `*` without losing callsign/SSID identity;
- arbitrary information bytes are escaped to a single stable line;
- malformed or metadata-inconsistent internal events are counted/skipped without affecting the TNC backend;
- a stalled monitor uses the existing bounded backend queue and existing subscriber-drop accounting;
- monitor APIs expose no write/TX operation;
- frozen AX.25/KISS/RX/P8 source blobs remain exact;
- existing AX.25, KISS, RX runtime and sustained P8 tests remain green;
- no UART, RF, GPIO, flash or option-byte activity occurs.

The roadmap item remains open until exact-head CI is green and host qualification evidence is frozen.
