# 0H-P8 mailbox forwarding integration

0H-P8 composes the frozen mailbox store and static forwarding policy into an inert work planner. Callers provide explicit message envelopes; the planner evaluates local delivery, hold, rejection, or an exact enabled route before reading any payload.

For a forward decision, the message ID is read under the envelope's exact destination identity. This prevents an ID from selecting another recipient's message. Prepared work contains immutable sender, destination, next hop, subject, appended trace, and body chunks no larger than 128 bytes. A batch contains at most eight unique message/destination pairs and preserves caller order.

The planner does not enumerate, schedule, connect, dispatch, acknowledge, delete, or update messages. It owns no clock, socket, thread, service, modem, persistent configuration, or RF path. The physically qualified P7 harness and evidence remain byte-exact.
