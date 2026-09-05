# 0G-P3 deterministic link timers

0G-P3 adds a host-only timing policy above the byte-frozen 0G-P2 modulo-8 data
link. It does not add a clock thread, event loop, terminal session, modem owner,
serial transport, or RF dispatch path. Every emitted `DataLinkAction` remains
inert until a future, separately qualified runtime chooses to consume it.

## Clock boundary

The caller supplies a finite monotonic `now` value to every operation and calls
`poll(now=...)` to evaluate deadlines. A late poll produces at most one retry;
the implementation never catches up by emitting several transmissions at once.
The default policy is T1=3 seconds, T2=1 second, T3=180 seconds, and N2=3.
Configuration is bounded, with T2 shorter than T1 and T3 longer than T1.

## T1 retry supervision

T1 supervises pending SABM and DISC exchanges, outstanding I frames, and a T3
idle enquiry. Expiry returns one inert retransmission set and rearms T1 until
the configured N2 limit is reached. Exhaustion fails closed: an unanswered
connection attempt returns to disconnected, an established data link emits one
inert DISC and enters awaiting release, and an unanswered release remains in
awaiting release without further automatic action.

## T2 delayed acknowledgement

T2 delays only a plain RR acknowledgement created after an in-sequence I frame.
An incoming Poll receives its Final response immediately. An outbound I frame
piggybacks the current N(R) and cancels the delayed RR. A due RR is returned once
from `poll` and is never dispatched by this layer.

## T3 idle enquiry

T3 runs only while connected. When idle and no T1 exchange is active, expiry
returns one RR command with Poll set and arms T1 to supervise that enquiry. A
matching supervisory Final cancels T1 and restarts the idle interval. T3 cannot
compete with connection, release, or outstanding-data supervision.

## Qualification boundary

Host tests cover each timer, modulo-8 data acknowledgements, bounded retry
exhaustion, teardown, Poll/Final behavior, and timer cancellation. A preservation
contract freezes P1, P2, the existing daemon, and the last physical 0F evidence,
and rejects imports or APIs that could activate runtime, serial, modem, or RF
behavior. Connected terminal sessions and multi-session policy remain deferred.
