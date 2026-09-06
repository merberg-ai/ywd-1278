# 0I-P4b persistent BBS product-backend service seam — host qualified

Date: 2026-09-06 UTC

Base checkpoint: `checkpoint/0i-p4a-persistent-bbs-runtime-host-qualified`
(`472bdadff2cf78ec83c1cac19fd321106a80b6bf`)

Candidate head: `0757a11ffb25f6df11d7c7aa56e6238ed8129bb9`

Candidate CI: `34008681299` — PASS

Qualified source blob:

- `src/ywd1278/service/persistent_bbs_service.py`
- Git blob `b816e786de1ca3acaeb1201857bf36db2d008dcf`

## Qualified behavior

- subscribes to the existing product PacketEvent backend rather than creating a second decoder;
- discards subscription history so stale frames cannot reopen or advance a BBS link after service restart;
- forwards only live, direct frames addressed to the configured local station into frozen P4a;
- submits every P4a AX.25 response through the existing backend `reject_client_message()` port-0 KISS DATA admission seam;
- requires product TX capability when the connected BBS is enabled;
- backend admission rejection latches the BBS service fail-closed and is not retried by this layer;
- irrelevant live frames are ignored;
- creates/reopens the configured dedicated persistent mailbox database;
- owns one bounded worker thread and one existing backend subscription only;
- stop joins the worker, unregisters the subscription, and leaves the persistent mailbox database intact.

Host loopback tests drive SABM/UA, connected BBS banner, SP composition, persistent
message deposit, LN/R delivery, irrelevant traffic, admission failure, history
suppression, and service stop through the backend seam.

## Preserved boundary

P4b still has no modem owner, UART implementation, Bell-202 decoder, CSMA policy,
TX queue implementation, firmware access, or direct RF path. The next P4
sub-boundary must prove the exact real product `TNCTransmitBackend`/qualified
DATA admission graph and daemon lifecycle before physical 0I-P5.

No target-Pi or RF test is required for P4b.
