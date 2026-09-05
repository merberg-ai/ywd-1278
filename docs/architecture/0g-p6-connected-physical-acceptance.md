# 0G-P6 guarded connected-mode product acceptance

P6 stages the first real product-path acceptance of the frozen P5 connected
stack. The harness temporarily starts the already-qualified product appliance
at 145.050 MHz with TX enabled, attaches through its loopback KISS interface,
and uses the public P5 manager boundary. It does not add connected mode to the
persistent daemon configuration.

The single authorized exchange targets the deployed BPQ node `KJ6YWD-5`
(`YWDNOD`). It requires a SABM/UA connection, sends exactly one new information
payload (`YWD-1278 0G-P6 CONNECTED TEST 1/1`), requires its outstanding window
to close through acknowledgement, and performs an orderly DISC/UA release.
P3 may retry according to its bounded N2 policy if RF loss occurs; the harness
does not invent a second retry mechanism.

Dry-run is the default and performs no service, UART, or RF operation. Physical
mode requires root, an exact command-line authorization token, the qualified
firmware image, eligibility validation, and a second exact interactive arm
phrase. Cleanup terminates the temporary daemon, removes its runtime directory,
restores the normal enabled no-TX service, and verifies that the persistent
configuration hash is unchanged.

Successful physical evidence will qualify real peer interoperability and RX/TX
recovery. Persistent console/daemon exposure of connected mode remains a later
product decision after this bounded acceptance succeeds.
