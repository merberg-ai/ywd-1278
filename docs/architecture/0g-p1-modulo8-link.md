# 0G-P1 modulo-8 link establishment and release

P1 introduces a pure, caller-driven AX.25 connected-mode state machine. It is
not wired to the console, packet backend, scheduler, modem, UART, or RF.

The link has four explicit states: `DISCONNECTED`, `AWAITING_CONNECTION`,
`CONNECTED`, and `AWAITING_RELEASE`. Local requests prepare inert direct SABM
or DISC frame bodies. Correctly addressed remote SABM, UA, DISC, and DM frames
drive deterministic transitions and may return inert UA or DM response bodies.

P1 enforces conventional AX.25 command/response address bits, Poll/Final on UA
completion, the configured peer identity, direct paths, and empty information
fields. Malformed, unrelated, unsupported, or semantically invalid frames do
not change link state. A simultaneous-open SABM is accepted and answered with
UA. A remote DM returns any pending or established link to disconnected mode.

V(S), V(R), and V(A) exist in the immutable snapshot and reset to zero on link
establishment or teardown. P1 also freezes validated modulo-8 increment and
forward-distance arithmetic. I frames, supervisory frames, payload queues,
MAXFRAME, flow control, T1/T2/T3 timers, retransmission, and connected terminal
sessions remain later 0G stages.
