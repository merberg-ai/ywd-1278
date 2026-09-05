"""0H-P4 authenticated, inert sysop command gate."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from ywd1278.ax25 import Address
from ywd1278.console.auth import CredentialRecord, encode_credential, verify_password

MAX_SYSOP_ATTEMPTS=3
class SysopActionType(Enum):
    STATUS="STATUS"; DELETE_MESSAGE="DELETE_MESSAGE"; ENABLE_ROUTE="ENABLE_ROUTE"; DISABLE_ROUTE="DISABLE_ROUTE"
@dataclass(frozen=True)
class SysopAction:
    action: SysopActionType
    message_id: int|None=None
    destination: Address|None=None
@dataclass(frozen=True)
class SysopResult:
    accepted: bool
    reason: str
    action: SysopAction|None=None
@dataclass(frozen=True)
class SysopSnapshot:
    authenticated: bool; locked: bool; attempts: int; actions_prepared: int

class SysopCommandGate:
    """Authenticate locally supplied credentials and prepare no-op admin intents."""
    def __init__(self, credential: CredentialRecord)->None:
        if not isinstance(credential,CredentialRecord): raise TypeError("credential must be CredentialRecord")
        encode_credential(credential)
        self._credential=credential; self._authenticated=False; self._locked=False; self._attempts=0; self._actions=0
    @property
    def snapshot(self)->SysopSnapshot: return SysopSnapshot(self._authenticated,self._locked,self._attempts,self._actions)
    def authenticate(self,username:str,password:str)->SysopResult:
        if self._locked: return SysopResult(False,"sysop authentication locked")
        if self._authenticated: return SysopResult(True,"sysop already authenticated")
        valid_user=isinstance(username,str) and username==self._credential.username
        valid_password=verify_password(password,self._credential.password_hash)
        if not (valid_user and valid_password):
            self._attempts+=1
            if self._attempts>=MAX_SYSOP_ATTEMPTS: self._locked=True
            return SysopResult(False,"sysop authentication failed")
        self._authenticated=True
        return SysopResult(True,"sysop authenticated")
    def prepare(self,line:str)->SysopResult:
        if not isinstance(line,str): raise TypeError("line must be str")
        if not self._authenticated or self._locked: return SysopResult(False,"sysop authentication required")
        if "\x00" in line or len(line.encode("utf-8"))>128: return SysopResult(False,"invalid sysop command")
        parts=line.strip().split(); command=parts[0].upper() if parts else ""
        action=None
        if command=="STATUS" and len(parts)==1: action=SysopAction(SysopActionType.STATUS)
        elif command=="MESSAGE" and len(parts)==3 and parts[1].upper()=="DELETE":
            try: message_id=int(parts[2],10)
            except ValueError: message_id=0
            if message_id>0: action=SysopAction(SysopActionType.DELETE_MESSAGE,message_id=message_id)
        elif command=="ROUTE" and len(parts)==3 and parts[1].upper() in ("ENABLE","DISABLE"):
            try: destination=Address.parse(parts[2])
            except ValueError: destination=None
            if destination is not None:
                kind=SysopActionType.ENABLE_ROUTE if parts[1].upper()=="ENABLE" else SysopActionType.DISABLE_ROUTE
                action=SysopAction(kind,destination=destination)
        if action is None: return SysopResult(False,"unknown or invalid sysop command")
        self._actions+=1
        return SysopResult(True,"inert sysop action prepared",action)
    def logout(self)->SysopResult:
        self._authenticated=False
        return SysopResult(True,"sysop logged out")

__all__=["MAX_SYSOP_ATTEMPTS","SysopActionType","SysopAction","SysopResult","SysopSnapshot","SysopCommandGate"]
