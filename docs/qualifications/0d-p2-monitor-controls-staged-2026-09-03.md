# 0D-P2 MCOM/MCON/MRPT-style monitor controls — staged

Base: `checkpoint/0d-p1-decoded-monitor-host-qualified` / `1972f4c92552085202c810e3b605c8e46275634c`

Development branch: `dev-0d-p2-monitor-controls`

P2 adds only a typed, thread-safe policy/view layer above frozen P1 `MonitorRecord`s. It deliberately does not add the 0E command shell early.

The familiar defaults are locked as `MCOM OFF`, `MCON OFF`, `MRPT ON`.

- **MCOM**: when OFF, AX.25 S frames and non-UI U protocol/control frames are suppressed from the monitor view. I and UI information frames remain eligible. Turning MCOM ON exposes those protocol/control frames.
- **MCON**: while a future local connected-mode session is active, OFF suppresses eligible third-party monitor traffic but still permits traffic identified by the future link layer as addressed to the local station. ON permits all otherwise-eligible monitor traffic. Until 0G exists, connection/address context is explicit injected data rather than guessed.
- **MRPT**: ON displays the complete P1 path including repeated `*` state. OFF removes path only from the rendered view; the immutable structured record retains the full path.

Policy updates are atomic and generation-tagged. One effective multi-field update increments generation exactly once; idempotent writes do not advance it.

Safety remains observation-only: P1 stream and all 0C blobs are hash-locked; no modem/TX imports, UART, RF, GPIO/reset, flash or option-byte behavior is introduced.
