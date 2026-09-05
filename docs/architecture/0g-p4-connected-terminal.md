# 0G-P4 connected terminal session

0G-P4 adds one deterministic, host-only terminal policy above the frozen P3
timed link. It defines how one operator session requests a direct connection,
enters connected text mode, prepares bounded I frames, displays received
information, returns to command mode, and requests release. It does not attach
that policy to the existing Telnet, PTY, daemon, appliance, KISS, modem, or RF
owners.

## Session commands and modes

Each `ConnectedTerminalSession` starts in command mode with a fixed local
address, MAXFRAME, PACLEN, and timer policy. `CONNECT DEST` selects exactly one
direct peer and returns an inert SABM action. A valid UA enters connected text
mode. An exact `COMMAND` line returns to command mode without releasing the
link; `CONVERSE` resumes text mode while connected. `CSTATUS` reports the
session-local state and `DISCONNECT` returns an inert DISC action.

There is no abbreviation engine, digipeater path, reconnect shortcut, shared
registry, or implicit peer selection in P4. Multi-session ownership and
arbitration remain deferred.

## Connected data boundary

One non-empty printable ASCII input line prepares at most one I frame through
the frozen P3/P2 path. The configured PACLEN and MAXFRAME window are enforced
before a frame can be returned. Rejected lines cannot advance V(S), and no
method dispatches a returned action.

Incoming I-frame information is delivered once. Printable ASCII is preserved;
control and non-ASCII bytes are rendered as visible `\\xNN` text so received
data cannot inject terminal controls. Link Poll/Final, acknowledgements,
retransmission sets, delayed RR, idle enquiry, and timeout behavior remain
owned by frozen P3.

## Failure and ownership boundary

Remote DISC/DM, completed release, and retry exhaustion return the terminal to
command mode. T1 exhaustion may return the one inert fail-closed DISC already
defined by P3. The caller supplies monotonic time to frame, line, and poll
operations; P4 creates no clock, worker, queue, socket, serial handle, modem
owner, or transmitter.

Host qualification freezes P3, P2, the existing daemon, and physical 0F
evidence. Runtime console integration and the policy for multiple simultaneous
sessions remain future stages and require separate qualification.
