# 0G-P5 multi-session ownership policy

0G-P5 wraps the frozen P4 connected terminal in a bounded, deterministic
session registry. Up to eight named local terminal sessions may exist, but
exactly one may own the native connected AX.25 link. This is an ownership
policy only: it creates no listener, PTY, worker, queue, modem connection, or
RF dispatch path.

The first valid `CONNECT` request receives the exclusive lease. While held, a
different session's connection request is rejected atomically without changing
either terminal. Frames and timer polls route only to the owner. Invalid
connection syntax releases a provisional lease immediately.

Closing an idle session removes it without touching the owner. Closing a
connected owner first returns to command mode, prepares one inert DISC through
P4/P3, and retains both the session and lease until release completes. Closing
an owner whose SABM is still pending cancels that attempt without manufacturing
a DISC. Remote release, DM, or failed connection timeout releases the lease so
another registered session may connect.

Session identifiers are unique, bounded safe-ASCII tokens and registration is
limited before allocation. Counters expose ownership generations and rejected
contention for later diagnostics. No fairness queue or automatic handoff is
implemented: a caller must retry after the current lease is released.

Host qualification freezes P4/P3 and prior physical evidence and proves that
existing console, daemon, appliance, KISS, serial, modem, and RF owners do not
import P5. Binding this policy to live console transports and the product TX/RX
graph requires a later, separately qualified integration stage.
