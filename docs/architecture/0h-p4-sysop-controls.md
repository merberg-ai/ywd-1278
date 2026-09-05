# 0H-P4 sysop controls

P4 defines a session-local authentication gate using the frozen protected
PBKDF2 credential format. A callsign never grants authority. Three failed
attempts permanently lock that gate instance; logout revokes a successful
session.

Authenticated exact commands can prepare typed STATUS, message deletion, and
route enable/disable intents. These objects are deliberately inert: P4 cannot
open or mutate the mailbox, replace forwarding policy, invoke a shell, control
services, access hardware, or transmit. A later product integration must map
each intent to an audited executor under separate qualification.
