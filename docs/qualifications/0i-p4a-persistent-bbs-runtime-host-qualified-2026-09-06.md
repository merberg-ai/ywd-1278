# 0I-P4a persistent connected BBS runtime — host qualified

Date: 2026-09-06 UTC

Base checkpoint: `checkpoint/0i-p3-node-mailbox-config-host-qualified`
(`12d5934a1be786601be123b6c4460ea5ad22a61e`)

Candidate head: `5ac31ddb7e952004aa925938ffd114d48a151aaa`

Candidate CI: `34008488519` — PASS

Qualified source blob:

- `src/ywd1278/node/persistent_bbs_runtime.py`
- Git blob `0c40aaf283142b71d16c9f30a1687865a98b197f`

## Qualified behavior

- dynamically accepts exactly one direct inbound SABM addressed to the configured local station;
- creates one frozen 0H-P5 inbound connected-session coordinator around the frozen 0I-P2 classic BBS personality and frozen 0I-P1 store;
- emits the familiar `YWDNOD:<local>} Connected to BBS` line followed by the classic persistent BBS banner/prompt;
- a second direct SABM contender while occupied is explicitly rejected with DM;
- connected policy is conservative MAXFRAME 1, receive PACLEN 256, T1 35 s, T2 1 s, T3 180 s, N2 2;
- body lines that intentionally produce no BBS text still receive the frozen timed-link T2 acknowledgement and do not stall the peer;
- host tests complete SP/list/read/kill/BYE, bulletin read-state persistence, runtime recreation over the same persistent store, and single-owner contention;
- BYE drains acknowledged responses before orderly connected-mode release.

## Preserved boundary

All returned AX.25 actions are inert. P4a owns no product backend, KISS admission,
CSMA dispatcher, modem/UART, thread, service lifecycle, or RF path. Product
backend/daemon composition is deliberately the next P4 sub-boundary before any
physical persistent-service test.

No target-Pi or RF test is required for P4a.
