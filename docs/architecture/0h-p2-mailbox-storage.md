# 0H-P2 mailbox storage

P2 adds a schema-versioned SQLite repository independent of the P1 command
parser. Messages have validated AX.25 sender/recipient identities, a 64-byte
printable ASCII subject, a 4096-byte printable ASCII/CR/LF body, and an explicit
caller-supplied non-negative timestamp. Writes use an immediate transaction and
enforce 100 messages per recipient and 1000 globally before insertion.

The database must use an absolute path beneath an existing directory. New files
are created mode 0600 without following symlinks; the device/inode identity is
checked around every connection. Unversioned non-empty or structurally altered
databases fail closed. Queries are parameterized, newest-first listings are
bounded to 100, and reads require the recipient identity.

There is no deletion, status mutation, forwarding, sysop override, background
thread, network listener, node-command binding, modem, or RF capability. Those
policies remain separately qualified later stages.
