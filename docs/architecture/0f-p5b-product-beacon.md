# 0F-P5b host product beacon composition

P5b introduces one product-wide coordinator above the frozen P5a state machine
and P4 submit adapter. The coordinator receives station identity and immutable
construction-time TX policy. It stores beacon text, destination/path, schedule,
and admission counters outside any individual console session.

An explicit caller tick can consume at most one due schedule event. It builds
one FCS-free AX.25 UI body and invokes the existing `ClassicTXSubmitter` once.
The existing adapter remains the only component that converts that call into a
port-zero KISS DATA message for `ProductTNCBackend.reject_client_message`.

Rejected or exceptional admissions are recorded once and are never retried.
When TX is disabled, no deadline is consumed and no submitter is invoked.

P5b deliberately does not wire a clock loop into the daemon. Timer lifecycle,
shutdown ordering, restart behavior, and command-session binding remain P5c.
There is no physical harness and no RF authorization in this stage.
