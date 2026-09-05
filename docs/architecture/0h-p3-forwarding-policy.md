# 0H-P3 forwarding policy

P3 evaluates immutable envelopes against at most 32 exact static routes. Local
destinations always deliver locally. Missing or disabled routes HOLD. Duplicate
trace entries, revisiting this node, exhausted hop limits, or selecting a next
hop already in the trace REJECT. A valid route returns its next hop and a trace
with this node appended.

The policy does not read or mutate mailbox storage, schedule connections,
retry, resolve aliases, wildcard destinations, open transports, or dispatch RF.
Every decision is inert input for later forwarding execution and sysop policy.
