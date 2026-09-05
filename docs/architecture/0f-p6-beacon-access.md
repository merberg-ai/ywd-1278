# 0F-P6 beacon jitter and channel-access gate

P6 adds one timing policy above the frozen P5 beacon coordinator. Every newly
armed or rescheduled event receives one non-negative random delay from zero to
10% of the configured interval, capped at 60 seconds. The base interval is
never shortened, and missed intervals still produce at most one event.

The jitter layer does not transmit. Once its release time arrives, it invokes
the frozen P5 coordinator exactly once. P5 then offers the frame to the same
product DATA admission boundary used by console and KISS traffic. The existing
bounded queue, RSSI detector, p-persistent CSMA, half-duplex lifecycle, TX
broker, and modem owner remain the only route to RF.

Invalid randomness fails closed by disarming the schedule. Shutdown and
explicit `BEACON OFF` also clear pending jitter state. A rejection or exception
is terminal for that scheduled event and is not retried.

Host qualification injects deterministic clock and byte sources. It proves a
maximum-jitter event cannot release early and proves through the full fake-HAT
daemon graph that a due event remains queued while CSMA rejects persistence,
then dispatches exactly once only after CSMA permits it. No physical RF is
needed for this host boundary; a later test may separately qualify the timing
policy on the target without authorizing unattended periodic RF.
