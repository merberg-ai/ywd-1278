# 0F-P5c beacon scheduler lifecycle safety

P5c wraps the frozen P5b coordinator in one named, non-daemon worker. The
worker waits before its first tick, rejects duplicate starts, and delegates
each tick to P5b's at-most-one admission boundary.

Stopping first signals cancellation, then joins any in-flight worker, and only
then forces coordinator schedule state OFF. Consequently, after `stop()`
returns there is neither a worker nor a deadline that can fire after restart.
A join timeout fails loudly rather than abandoning a live transmitter thread.

Unexpected coordinator exceptions terminate the worker and disarm the
schedule. They are never treated as permission to retry an uncertain frame.

P5c remains host-only. The scheduler is not constructed by the daemon, no
configuration enables it, and no physical harness, UART, modem, or RF path is
introduced. Product daemon wiring and any physical event remain separately
gated.
