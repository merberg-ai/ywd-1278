# 0G-P2 I-frame sequencing and supervisory acknowledgements

P2 composes the frozen P1 link state and adds a bounded modulo-8 data-link
model. It remains pure and caller-driven: frames returned by the model are
inert byte strings and delivered information is returned directly to the
caller.

The send side enforces PACLEN and a configurable MAXFRAME window of 1..7.
V(S) advances only when a new I frame is prepared. V(A) advances only through
a valid cumulative N(R) within the current outstanding window. Invalid
acknowledgements are atomic and do not discard queued frame state.

The receive side accepts the expected N(S), advances V(R), returns the payload
once, and prepares RR. An unexpected or duplicate N(S) prepares REJ without
delivery. Local receive-busy state prepares RNR and prevents V(R) advancement.
Remote RNR blocks new I-frame preparation until RR or REJ clears it.

REJ cumulatively acknowledges through its N(R) and returns the remaining
outstanding frames as explicitly marked, inert retransmission actions. P2 does
not schedule or execute them. Poll commands receive the matching Final RR/RNR
response. Fresh SABM, completed release, DISC, or DM reset all P2 sequence,
window, and busy state.

P2 has no timer, automatic retry, worker, queue thread, socket, console,
product-runtime connection, KISS admission, modem, UART, or RF capability.
Timer ownership, retry counts, delayed acknowledgements, and connected terminal
integration remain later stages.
