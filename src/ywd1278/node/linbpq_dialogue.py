"""0H-P9 caller-driven classic LinBPQ personal-message dialogue."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

from ywd1278.ax25 import Address
from ywd1278.node.forwarding_integration import PreparedForwardMessage

MAX_REMOTE_BUFFER_BYTES=512
MAX_REMOTE_LINES=64

class LinBPQState(Enum):
 WAIT_BANNER="WAIT_BANNER"
 WAIT_TITLE_PROMPT="WAIT_TITLE_PROMPT"
 WAIT_BODY_PROMPT="WAIT_BODY_PROMPT"
 WAIT_ACCEPT="WAIT_ACCEPT"
 COMPLETE="COMPLETE"
 FAILED="FAILED"

@dataclass(frozen=True)
class LinBPQAction:
    kind: str
    data: bytes

@dataclass(frozen=True)
class LinBPQResult:
    accepted: bool
    reason: str
    actions: tuple[LinBPQAction,...]=()

@dataclass(frozen=True)
class LinBPQSnapshot:
    state: LinBPQState
    remote_lines: int
    sid_seen: bool
    prompt_seen: bool
    buffered_bytes: int
    actions_prepared: int

class LinBPQPersonalDelivery:
    """Consume remote text and prepare inert classic-BBS input bytes."""
    def __init__(self, *, work: PreparedForwardMessage, bbs: Address,
                 prompt_callsign: str) -> None:
        if not isinstance(work,PreparedForwardMessage): raise TypeError("work must be PreparedForwardMessage")
        if not isinstance(bbs,Address): raise TypeError("bbs must be an AX.25 Address")
        if work.next_hop!=Address(bbs.callsign,bbs.ssid): raise ValueError("work next hop must match BBS")
        prompt=prompt_callsign.strip().upper()
        if not prompt or not prompt.isascii() or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in prompt):
            raise ValueError("prompt_callsign must be an ASCII callsign")
        self._work=work; self._bbs=Address(bbs.callsign,bbs.ssid); self._prompt=prompt
        self._state=LinBPQState.WAIT_BANNER; self._buffer=bytearray(); self._lines=0
        self._sid_seen=False; self._prompt_seen=False; self._actions=0

    @property
    def snapshot(self)->LinBPQSnapshot:
        return LinBPQSnapshot(self._state,self._lines,self._sid_seen,self._prompt_seen,len(self._buffer),self._actions)

    def feed(self, data: bytes)->LinBPQResult:
        if not isinstance(data,bytes): raise TypeError("data must be bytes")
        if self._state in (LinBPQState.COMPLETE,LinBPQState.FAILED):
            return LinBPQResult(False,"LinBPQ delivery is terminal")
        if len(self._buffer)+len(data)>MAX_REMOTE_BUFFER_BYTES: return self._fail("remote text buffer overflow")
        self._buffer.extend(data); actions=[]; reasons=[]
        while True:
            sep=next((i for i,v in enumerate(self._buffer) if v in (10,13)),None)
            if sep is None: break
            raw=bytes(self._buffer[:sep]); end=sep+1
            while end<len(self._buffer) and self._buffer[end] in (10,13): end+=1
            del self._buffer[:end]
            if raw:
                result=self._line(raw); reasons.append(result.reason); actions.extend(result.actions)
                if self._state is LinBPQState.FAILED: return LinBPQResult(False,result.reason,tuple(actions))
        if self._buffer.endswith(b">"):
            raw=bytes(self._buffer); self._buffer.clear(); result=self._line(raw)
            reasons.append(result.reason); actions.extend(result.actions)
        if not reasons: return LinBPQResult(True,"partial remote line buffered")
        return LinBPQResult(self._state is not LinBPQState.FAILED,"; ".join(reasons),tuple(actions))

    def _line(self,raw:bytes)->LinBPQResult:
        self._lines+=1
        if self._lines>MAX_REMOTE_LINES: return self._fail("remote line limit exceeded")
        try: text=raw.decode("ascii")
        except UnicodeDecodeError: return self._fail("remote line is not ASCII")
        normalized=text.strip(); lower=normalized.lower()
        if any(word in lower for word in ("invalid", "unknown command", "failed", "failure", "not allowed")):
            return self._fail(f"BBS rejected delivery: {normalized}")
        if normalized.startswith("[BPQ-") and normalized.endswith("]"):
            self._sid_seen=True; return LinBPQResult(True,"BPQ SID observed")
        if self._is_prompt(normalized):
            self._prompt_seen=True
            if self._state is LinBPQState.WAIT_BANNER:
                if not self._sid_seen: return self._fail("BBS prompt arrived before BPQ SID")
                self._state=LinBPQState.WAIT_TITLE_PROMPT
                return self._emit("SP",f"SP {self._work.destination}\r".encode())
            if self._state is LinBPQState.WAIT_ACCEPT:
                self._state=LinBPQState.COMPLETE
                return LinBPQResult(True,"BBS prompt returned after message submission")
        if self._state is LinBPQState.WAIT_TITLE_PROMPT and ("title" in lower or "subject" in lower):
            self._state=LinBPQState.WAIT_BODY_PROMPT
            return self._emit("TITLE",self._work.subject.encode("ascii")+b"\r")
        if self._state is LinBPQState.WAIT_BODY_PROMPT and ("message" in lower or "/ex" in lower):
            self._state=LinBPQState.WAIT_ACCEPT
            output=[LinBPQAction("BODY",chunk) for chunk in self._work.body_chunks]
            body_ends_line=bool(self._work.body_chunks and self._work.body_chunks[-1].endswith((b"\r",b"\n")))
            if not body_ends_line: output.append(LinBPQAction("BODY_END",b"\r"))
            output.append(LinBPQAction("END",b"/EX\r")); self._actions+=len(output)
            return LinBPQResult(True,"message body and terminator prepared",tuple(output))
        return LinBPQResult(True,"remote informational line accepted")

    def _is_prompt(self,text:str)->bool:
        return text.upper()==f"DE {self._prompt}>"
    def _emit(self,kind:str,data:bytes)->LinBPQResult:
        self._actions+=1; return LinBPQResult(True,f"{kind} action prepared",(LinBPQAction(kind,data),))
    def _fail(self,reason:str)->LinBPQResult:
        self._state=LinBPQState.FAILED; self._buffer.clear(); return LinBPQResult(False,reason)

__all__=["MAX_REMOTE_BUFFER_BYTES","MAX_REMOTE_LINES","LinBPQState","LinBPQAction","LinBPQResult","LinBPQSnapshot","LinBPQPersonalDelivery"]
