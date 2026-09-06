# 0H-P10 R3 LinBPQ physical delivery staging

R1 and R2 both proved live delivery through `/EX`, but neither observed the returned LinBPQ command prompt. The BBS-side log for the R2 attempt shows that LinBPQ accepted the message, stored it, generated the post-submit text immediately, and only later disconnected the still-open AX.25 link. The YWD-1278 harness remained in `WAIT_ACCEPT`.

R2 already removed the larger outbound window by forcing stop-and-wait (`MAXFRAME=1`), so R3 does not change the frozen P9 dialogue or any bytes it emits.

## R3 correction

The original P10 link instance used `paclen=128` for both outbound and inbound connected information. P10 independently limits every outbound information submission to 128 bytes, but LinBPQ is permitted to send larger connected information frames. The observed post-submit application text is approximately 146 bytes if coalesced into one information frame, and prior packet captures from this LinBPQ installation include connected I frames of 196 bytes.

R3 therefore:

- preserves R2 stop-and-wait (`MAXFRAME=1`);
- raises only the effective connected link PACLEN to 256 bytes so inbound LinBPQ I frames up to 256 bytes may be accepted;
- preserves P10's independent outbound `1..128` byte guard;
- preserves the exact P9 action sequence and bytes;
- adds a diagnostic line for any inbound AX.25 frame rejected by the link layer.

The pre-RF R3 contract proves that a 196-byte remote I frame is rejected by the R2 128-byte link, accepted and delivered by R3, and that 257-byte inbound information still fails closed.

No firmware, P9, P8, P7, persistent configuration, mailbox storage, or normal runtime wiring is changed by R3.
