# 0D-P1 decoded monitor stream — host qualified

0D-P1 is host-qualified above the frozen 0C persistent bidirectional TNC checkpoint.

## Frozen base

- checkpoint: `checkpoint/0c-complete-p8-physical-qualified`
- base SHA: `fc70386a3857e69437641d1be6f9f8cd0a6e7a13`
- qualified implementation head: `164f0a6b5d8976f94f5824c1224d778a2ef40e99`
- monitor implementation blob: `703b7e803d39d915b60d79c30c154151e3820098`

No 0C/P8 implementation source was changed.

## Qualified behavior

The monitor consumes the already-qualified `PacketEvent` boundary by calling `RXOnlyBackend.open_stream()`. Each reader receives bounded history first and then the existing bounded live subscriber queue in source order. No monitor worker thread or second queue is introduced.

Records preserve AX.25 source, destination, path/repeated `*` state, frame class/type, P/F, N(S), N(R), PID, information bytes and original no-FCS body. UI/PID-F0 traffic renders in familiar one-line TNC2 form; I/S/U traffic retains explicit frame metadata for later monitor-control filtering. Arbitrary payload bytes are escaped so terminal/log output remains one line.

Malformed or metadata-inconsistent internal events are counted and skipped without mutating the packet backend. A stalled monitor remains bounded by the existing subscriber queue and existing `subscriber_drops` accounting.

The public monitor surface has no publish/transmit operation and imports no modem or TX layer.

## CI evidence

Dedicated push CI run `33814562850` passed on the exact implementation head. Draft PR #25 then triggered 14 repository PR workflows on the same SHA, including framework-ci run `33814566960`; all completed successfully with zero pending and zero failed runs.

The qualification contracts also hash-lock the frozen AX.25 codec, KISS backend/control/sustained/TX path, RX runtime and P8 TNC runtime.

## Safety boundary

0D-P1 is host-only and observation-only: no UART, modem transaction, RX/TX radio configuration, RF transmission, GPIO/reset, flash, or option-byte activity is reachable through the monitor API.

MCOM/MCON/MRPT-style controls, SQLite persistence, MHEARD, retention and aggregate diagnostics remain later 0D stages.
