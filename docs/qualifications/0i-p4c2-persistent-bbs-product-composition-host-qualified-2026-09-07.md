# 0I-P4c2 persistent BBS product composition — host qualified

Date: 2026-09-07 UTC

Integration base: `dev` at
`b92d1b2dd8195003f901f6df2142946cc2ca7085`.

Frozen mailbox service lineage:
`checkpoint/0i-p4b-persistent-bbs-product-service-host-qualified` at
`8103bf095ebd1bd96c0f65800382718557890340`.

Host-qualified candidate:
`c90c81426ab09ce60587a236a093fb5c5bddfa41`

Candidate tree:
`67e579f982135b56f1baa94d8b9ca0ae16621912`

Dedicated exact-tip CI:
- workflow: `0i-p4c2-persistent-bbs-product-composition-ci`
- run: `34121711854`
- job: `host-pre-rf`
- result: PASS

## Frozen production composition

The qualified candidate preserves these exact production blobs:

- `src/ywd1278/daemon.py`
  - `85471ccac9e26079c0265753054d54eb1753e191`
- `src/ywd1278/service/product_mailbox_console.py`
  - `93c9a66be6b5d01d6bacfb70b2eef7b1189a9b6c`
- `src/ywd1278/service/appliance.py`
  - `fa1b086d6d8fa40b537c002dbeec34fdc6532396`
- `src/ywd1278/service/persistent_bbs_service.py`
  - `b816e786de1ca3acaeb1201857bf36db2d008dcf`
- `src/ywd1278/node/persistent_bbs_runtime.py`
  - `0c40aaf283142b71d16c9f30a1687865a98b197f`
- `src/ywd1278/node/classic_bbs.py`
  - `e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd`
- `src/ywd1278/node/persistent_mailbox.py`
  - `f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc`
- `src/ywd1278/service/node_mailbox_config.py`
  - `a56d8981888ebffd1aa22d895d53db7326e9d6bc`

Host qualification evidence additionally freezes:

- `tests/persistent_bbs_product_composition_0i_p4c2_test.py`
  - `10b8bf588a23ee797bcff53eaee3909c06853cb4`
- `tests/persistent_bbs_product_composition_0i_p4c2_contract_test.py`
  - `2816e42a930a064d223924b2f165a1b6fb510e33`
- `docs/qualifications/0i-p4c2-persistent-bbs-product-composition-pre-rf.md`
  - `7b8edc5483f32735ebe0dd1be2b81832b3a6d6f1`
- `tests/persistent_bbs_product_composition_0i_p4c2_pre_rf_contract_test.py`
  - `04ed7b7ed7fb226f02ff923baa6010272ab0d668`
- `.github/workflows/0i-p4c2-persistent-bbs-product-composition-ci.yml`
  - `04b481e8f0f4058270b45fb09144327290bc23bb`

## Qualified behavior

### Local MFJ-style mailbox personality

From the normal product terminal, `MBOX` enters the same persistent mailbox
used by the connected RF BBS. It does not create a second database or synthetic
remote user. The configured station identity is used for the local mailbox
identity, with the existing base-callsign cross-SSID semantics.

A local terminal can return to `cmd:` with:

- `/CMD`
- `COMMAND`
- raw Ctrl-C
- `BYE`

Those escapes do not close the enclosing Telnet/PTTY session. A raw Ctrl-C also
discards an unfinished local MBOX line so partial text cannot contaminate the
next command-mode input. Local SP/LN/R and other mailbox operations perform no
packet submission and no RF action.

### Exact real product backend composition

The host test constructs the actual `ProductTNCBackend`, actual
`ThreadSafeKISSDataAdmissionQueue`, actual `TNCSessionState`, actual persistent
BBS service/runtime, and actual persistent SQLite mailbox. Only the final
contextual hardware/RF submitter is replaced by an inert recording edge.

The test proves:

- the BBS service subscribes to the exact real `ProductTNCBackend` using its
  existing `open_stream()` PacketEvent interface;
- a live direct SABM reaches the persistent BBS runtime through that stream;
- UA and the first connected BBS banner I-frame return through the same real
  backend's port-0 KISS DATA admission path;
- admission alone never calls the fake final edge;
- explicit qualified clear-channel/RSSI observations are required before the
  existing bounded DATA queue dispatches an admitted response;
- admitted actions dispatch exactly once at that boundary;
- generated frames carry valid AX.25 FCS and the expected peer identity;
- service stop unregisters the BBS backend subscription and preserves the
  persistent mailbox database;
- `product_tx_enabled=false` rejects port-0 DATA before queue admission and
  leaves queue depth, dispatch count, and final-edge call count at zero;
- the connected BBS service itself refuses construction without persistent
  product TX authority.

### Daemon lifecycle and shared ownership

Static and behavioral contracts prove the normal daemon has one
`ProductPacketEngine` and uses its one `engine.backend` for both normal classic
TX submission and connected-BBS response admission. Local `MBOX` receives the
same `PersistentMailboxStore` object opened by the BBS service. Startup, health
checking, stop ordering, backend subscription cleanup, and package/framework
self-test all pass.

## Preserved boundary

P4c2 adds no second modem owner, Bell-202 decoder, UART reader, KISS DATA queue,
channel-access engine, scheduler, application-level TX retry, background TX
daemon, firmware writer, option-byte writer, GPIO path, or alternate RF path.
Connected AX.25 link semantics retain only the already-qualified frozen link
behavior; P4c2 adds no new retransmission policy.

Frozen P4b/P4a/P3/P2/P1 regressions and the existing product terminal
regressions remain green in the dedicated exact-tip run.

## Physical boundary

This qualification was host-only. No target Pi was modified or exercised for
P4c2, no modem UART was opened, no HAT was accessed, no firmware or option bytes
were written, and no RF was transmitted.

Qualification state:

- `MODEM_UART_OPENED=NO`
- `RF_TRANSMITTED=NO`
- `FIRMWARE_WRITTEN=NO`
- `OPTION_BYTES_WRITTEN=NO`

The next stage may define the bounded physical persistent-BBS qualification on
145.050 MHz. No physical test command is authorized or supplied by this host
qualification.
