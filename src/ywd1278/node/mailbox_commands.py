"""0H-P6 bounded mailbox commands above the frozen P1/P2 capabilities."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from ywd1278.ax25 import Address
from ywd1278.node.commands import MAX_NODE_BUFFER_BYTES, MAX_NODE_COMMAND_BYTES, NodeCommandSession
from ywd1278.node.mailbox import MailboxError, MailboxQuotaError, MailboxStore, MAX_BODY_BYTES

READ_WINDOW_BYTES = 512
RESPONSE_CHUNK_BYTES = 96
DEFAULT_LIST_LIMIT = 10
MAX_LIST_RESULTS = 12

@dataclass(frozen=True)
class MailboxCommandSnapshot:
    peer: str
    buffered_bytes: int
    commands: int
    rejected: int
    composing: bool
    compose_bytes: int
    close_requested: bool

@dataclass(frozen=True)
class MailboxCommandResult:
    accepted: bool
    reason: str
    responses: tuple[bytes, ...] = ()
    close_requested: bool = False

class MailboxNodeSession:
    """CR/LF command session whose peer identity owns all mailbox access."""
    def __init__(self, *, callsign: Address, peer: Address, alias: str,
                 store: MailboxStore, clock_ns: Callable[[], int]) -> None:
        if not isinstance(callsign, Address) or not isinstance(peer, Address):
            raise TypeError("callsign and peer must be AX.25 Address values")
        if not isinstance(store, MailboxStore): raise TypeError("store must be MailboxStore")
        if not callable(clock_ns): raise TypeError("clock_ns must be callable")
        self._local=Address(callsign.callsign,callsign.ssid)
        self._peer=Address(peer.callsign,peer.ssid)
        self._base=NodeCommandSession(callsign=self._local,alias=alias)
        self._store=store; self._clock_ns=clock_ns; self._buffer=bytearray()
        self._commands=0; self._rejected=0
        self._compose_recipient: Address|None=None; self._compose_subject=""
        self._compose_body=bytearray()

    @property
    def snapshot(self)->MailboxCommandSnapshot:
        return MailboxCommandSnapshot(str(self._peer),len(self._buffer),self._commands,
            self._rejected,self._compose_recipient is not None,len(self._compose_body),
            self._base.snapshot.close_requested)

    def banner(self)->tuple[bytes,...]:
        return (f"YWD-1278 NODE {self._base.snapshot.alias}:{self._local}\r".encode(),
                b"Mailbox ready; type HELP for commands\r")

    def feed(self, information: bytes)->MailboxCommandResult:
        if not isinstance(information,bytes): raise TypeError("information must be bytes")
        if self._base.snapshot.close_requested: return self._reject("node session is closed",close=True)
        if len(self._buffer)+len(information)>MAX_NODE_BUFFER_BYTES:
            self._buffer.clear(); return self._reject("node command buffer overflow")
        self._buffer.extend(information); responses=[]; accepted=True; processed=0
        while True:
            sep=next((i for i,v in enumerate(self._buffer) if v in (10,13)),None)
            if sep is None: break
            raw=bytes(self._buffer[:sep]); end=sep+1
            while end<len(self._buffer) and self._buffer[end] in (10,13): end+=1
            del self._buffer[:end]
            if not raw and self._compose_recipient is None: continue
            processed+=1; result=self._execute(raw); accepted &= result.accepted
            responses.extend(result.responses)
            if result.close_requested: self._buffer.clear(); break
        if not processed: return MailboxCommandResult(True,"partial command buffered")
        return MailboxCommandResult(accepted,f"processed {processed} line(s)",tuple(responses),self._base.snapshot.close_requested)

    def _execute(self,raw:bytes)->MailboxCommandResult:
        if len(raw)>MAX_NODE_COMMAND_BYTES: return self._reject("node line exceeds 128 bytes")
        try: text=raw.decode("ascii")
        except UnicodeDecodeError: return self._reject("node line must be ASCII")
        if any(ord(c)<32 or ord(c)>126 for c in text): return self._reject("node line must be printable ASCII")
        if self._compose_recipient is not None: return self._compose_line(raw,text)
        self._commands+=1; parts=text.strip().split(); command=parts[0].upper() if parts else ""
        args=parts[1:]
        if command in ("HELP","?") and not args:
            return self._ok("HELP                 show commands","LIST [limit]         list your messages",
                "READ <id> [offset]   read your message","SP <call> <subject>  compose a message",
                "/EX                  save composed message","/ABORT               abandon composition",
                "INFO VERSION BYE     node information and exit")
        if command=="LIST": return self._list(args)
        if command=="READ": return self._read(args)
        if command in ("SP","SEND"): return self._start_compose(args)
        if command=="INFO" and not args:
            return self._ok(f"NODE {self._base.snapshot.alias}:{self._local}",
                            f"MAILBOX OWNER {self._peer}","Local message deposit, list and paged read available")
        base=self._base.feed(raw+b"\r")
        return MailboxCommandResult(base.accepted,base.reason,base.responses,base.close_requested)

    def _list(self,args:list[str])->MailboxCommandResult:
        if len(args)>1: return self._reject("usage: LIST [limit]")
        try: limit=DEFAULT_LIST_LIMIT if not args else int(args[0],10)
        except ValueError: return self._reject("LIST limit must be an integer")
        if not 1<=limit<=MAX_LIST_RESULTS: return self._reject("LIST limit must be 1..12")
        try: items=self._store.list_for(self._peer,limit=limit)
        except MailboxError as exc: return self._reject(f"mailbox unavailable: {exc}")
        if not items: return self._ok("NO MESSAGES")
        lines=[f"MESSAGES {len(items)} NEWEST FIRST"]
        lines.extend(f"{x.message_id} FROM {x.sender} {x.body_bytes}B {x.subject}" for x in items)
        return self._ok(*lines)

    def _read(self,args:list[str])->MailboxCommandResult:
        if len(args) not in (1,2): return self._reject("usage: READ <id> [offset]")
        try: message_id=int(args[0],10); offset=0 if len(args)==1 else int(args[1],10)
        except ValueError: return self._reject("READ id and offset must be integers")
        if message_id<1 or offset<0: return self._reject("READ id must be positive and offset non-negative")
        try: message=self._store.read_for(self._peer,message_id)
        except (MailboxError,ValueError) as exc: return self._reject(f"mailbox unavailable: {exc}")
        if message is None: return self._reject("message not found for connected peer")
        if offset>len(message.body): return self._reject("READ offset exceeds message body")
        end=min(len(message.body),offset+READ_WINDOW_BYTES); portion=message.body[offset:end]
        responses=[f"MSG {message.message_id} FROM {message.sender} TO {message.recipient}\r".encode(),
                   f"SUBJECT {message.subject}\r".encode(),f"BODY {offset}:{end}/{len(message.body)}\r".encode()]
        for start in range(0,len(portion),RESPONSE_CHUNK_BYTES):
            responses.append(portion[start:start+RESPONSE_CHUNK_BYTES]+b"\r")
        responses.append((f"MORE READ {message_id} {end}\r" if end<len(message.body) else "END MESSAGE\r").encode())
        return MailboxCommandResult(True,"message window read",tuple(responses))

    def _start_compose(self,args:list[str])->MailboxCommandResult:
        if len(args)<2: return self._reject("usage: SP <callsign> <subject>")
        try: recipient=Address.parse(args[0])
        except (TypeError,ValueError): return self._reject("invalid recipient callsign")
        subject=" ".join(args[1:])
        try: subject.encode("ascii")
        except UnicodeEncodeError: return self._reject("subject must be ASCII")
        if not subject or len(subject.encode())>64 or any(ord(c)<32 or ord(c)>126 for c in subject):
            return self._reject("subject must be 1..64 printable ASCII bytes")
        self._compose_recipient=recipient; self._compose_subject=subject; self._compose_body.clear()
        return self._ok(f"ENTER MESSAGE FOR {recipient}; END WITH /EX OR CANCEL WITH /ABORT")

    def _compose_line(self,raw:bytes,text:str)->MailboxCommandResult:
        marker=text.strip().upper()
        if marker=="/ABORT": self._clear_compose(); return self._ok("MESSAGE ABORTED")
        if marker=="/EX":
            if not self._compose_body: return self._reject("message body is empty")
            assert self._compose_recipient is not None
            body=bytes(self._compose_body[:-1])
            try: timestamp=self._clock_ns()
            except Exception: self._clear_compose(); return self._reject("mailbox clock failed")
            try: message=self._store.deposit(sender=self._peer,recipient=self._compose_recipient,
                    subject=self._compose_subject,body=body,created_at_ns=timestamp)
            except (MailboxError,MailboxQuotaError,TypeError,ValueError) as exc:
                self._clear_compose(); return self._reject(f"message not saved: {exc}")
            self._clear_compose(); return self._ok(f"MESSAGE {message.message_id} SAVED FOR {message.recipient}")
        addition=raw+b"\r"
        if len(self._compose_body)+len(addition)>MAX_BODY_BYTES:
            self._clear_compose(); return self._reject("message body exceeds 4096 bytes; composition aborted")
        self._compose_body.extend(addition); return MailboxCommandResult(True,"message line buffered")

    def _clear_compose(self)->None:
        self._compose_recipient=None; self._compose_subject=""; self._compose_body.clear()
    @staticmethod
    def _ok(*lines:str)->MailboxCommandResult:
        return MailboxCommandResult(True,"mailbox command accepted",tuple((x+"\r").encode() for x in lines))
    def _reject(self,reason:str,*,close:bool=False)->MailboxCommandResult:
        self._rejected+=1; return MailboxCommandResult(False,reason,(f"ERROR {reason}\r".encode(),),close)

__all__=["READ_WINDOW_BYTES","RESPONSE_CHUNK_BYTES","MAX_LIST_RESULTS","MailboxCommandSnapshot","MailboxCommandResult","MailboxNodeSession"]
