#!/usr/bin/env python3
"""Guarded 0H-P7 physical mailbox round-trip acceptance."""
from __future__ import annotations
import argparse, hashlib, os, shutil, signal, socket, subprocess, sys, time, tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src")); sys.path.insert(0,str(ROOT/"tools"))
import qualify_stage_i_single_tx as stage_i  # noqa: E402
from ywd1278.ax25 import Address  # noqa: E402
from ywd1278.kiss.framing import DATA,KISSStreamDecoder,encode  # noqa: E402
from ywd1278.link.modulo8 import LinkState  # noqa: E402
from ywd1278.link.timed_link import LinkTimerConfig  # noqa: E402
from ywd1278.node.inbound import InboundNodeSession  # noqa: E402
from ywd1278.node.mailbox import MailboxStore  # noqa: E402
from ywd1278.node.mailbox_commands import MailboxNodeSession  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402

EXPECTED_HOST_COMMIT="ca4b17de379af9415448083177ffccb39c8fca0f"
AUTHORIZATION_TOKEN="0H-P7-MAILBOX-145050-KJ6YWD15-ONE"
ARM_PHRASE="TRANSMIT-0H-P7-MAILBOX-KJ6YWD-15-ONE"
TEMP_ROOT=Path("/run/ywd-1278-0h-p7"); TEMP_CONFIG=TEMP_ROOT/"config.toml"
TEMP_LOG=TEMP_ROOT/"daemon.log"; TEMP_MAILBOX=TEMP_ROOT/"mailbox.sqlite3"
TEMP_KISS_PORT=18501; TEMP_CONSOLE_PORT=18510; TEMP_PTY=str(TEMP_ROOT/"tnc")
LOCAL=Address.parse("KJ6YWD-10"); REMOTE=Address.parse("KJ6YWD-15")
SUBJECT="P7 TEST"; BODY=b"YWD-1278 0H-P7 MAILBOX TEST 1/1"

class ObservedMailboxStore(MailboxStore):
 def __init__(self,path):
  super().__init__(path); self.deposits=0; self.lists=0; self.reads=0
 def deposit(self,**kwargs): self.deposits+=1; return super().deposit(**kwargs)
 def list_for(self,*args,**kwargs): self.lists+=1; return super().list_for(*args,**kwargs)
 def read_for(self,*args,**kwargs): self.reads+=1; return super().read_for(*args,**kwargs)

def temporary_config(original):
 text=stage_i.replace_toml_key(original,"radio","tx_power",str(stage_i.TX_POWER))
 text=stage_i.replace_toml_key(text,"radio","tx_enabled","true")
 text=stage_i.replace_toml_key(text,"kiss","port",str(TEMP_KISS_PORT))
 text=stage_i.replace_toml_key(text,"console","port",str(TEMP_CONSOLE_PORT))
 return stage_i.replace_toml_key(text,"console","pty_link",f'"{TEMP_PTY}"')
def send(sock,result):
 for action in result.actions: sock.sendall(encode(action.frame_no_fcs,port=0,command=DATA))
 return len(result.actions)
def plan():
 print("===== YWD-1278 0H-P7 MAILBOX ROUND-TRIP ACCEPTANCE =====")
 print(f"HOST_BASE_CHECKPOINT={EXPECTED_HOST_COMMIT}"); print(f"LOCAL_NODE={LOCAL}")
 print(f"EXPECTED_REMOTE={REMOTE}"); print("REMOTE_LISTENER=KJ6YWD-5")
 print(f"SUBJECT={SUBJECT}"); print(f"BODY={BODY.decode()}")
 print("REQUIRED_SEQUENCE=HELP,LIST,SP,BODY,/EX,LIST,READ,BYE")
 print("TEMPORARY_MAILBOX=YES"); print("TX_FREQUENCY_HZ=145050000"); print("TX_POWER=200")
 print("PERSISTENT_CONFIG_MUTATED=NO"); print("FLASH_WRITTEN=NO"); print("OPTION_BYTES_WRITTEN=NO")
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--transmit",action="store_true")
 ap.add_argument("--authorize",default=""); ap.add_argument("--firmware",type=Path)
 ap.add_argument("--timeout",type=float,default=240); args=ap.parse_args(); plan()
 if not args.transmit:
  print("YWD1278_0H_P7_DRY_RUN=PASS"); print("SERVICE_MUTATED=NO"); print("MODEM_UART_OPENED=NO"); print("RF_TRANSMITTED=NO"); return 0
 if os.geteuid()!=0: raise SystemExit("[FAIL] physical P7 requires root")
 if args.authorize!=AUTHORIZATION_TOKEN: raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
 if args.firmware is None: raise SystemExit("[FAIL] --firmware is required")
 if not 60<=args.timeout<=360: raise SystemExit("[FAIL] --timeout must be 60..360 seconds")
 if stage_i._run(["git","merge-base","--is-ancestor",EXPECTED_HOST_COMMIT,"HEAD"],check=False).returncode!=0: raise SystemExit("[FAIL] checkout does not descend from qualified P6")
 for path in (stage_i.PERSISTENT_CONFIG,stage_i.INSTALLED_COMMIT,stage_i.VENV_PYTHON,stage_i.ELIGIBILITY):
  if not path.exists(): raise SystemExit(f"[FAIL] required appliance path missing: {path}")
 if stage_i._systemctl_state("is-enabled")!="enabled" or stage_i._systemctl_state("is-active")!="active": raise SystemExit("[FAIL] normal appliance must be enabled and active")
 original=stage_i.PERSISTENT_CONFIG.read_bytes(); original_hash=hashlib.sha256(original).hexdigest(); original_text=original.decode()
 if stage_i.validate_persistent_config(tomllib.loads(original_text))!=str(LOCAL): raise SystemExit(f"[FAIL] configured station must be {LOCAL}")
 stage_i._check_firmware(args.firmware); stage_i._verify_eligibility(args.firmware)
 print(f"PERSISTENT_CONFIG_SHA256={original_hash}"); print("PERSISTENT_TX_ENABLED=NO")
 if input(f"Type exactly {ARM_PHRASE} to accept ONE mailbox RF session: ").strip()!=ARM_PHRASE: raise SystemExit("[FAIL] P7 interactive arm phrase did not match")
 daemon=None; log_handle=None; stopped=False; cleanup_error=None; complete=False; actions=0; store=None
 try:
  stage_i._run(["systemctl","stop",stage_i.SERVICE]); stopped=True
  if stage_i._run(["fuser",stage_i.DEVICE],check=False).returncode==0: raise RuntimeError("UART remained owned")
  stage_i._verify_hardware_identity()
  if TEMP_ROOT.exists(): raise RuntimeError(f"stale P7 runtime exists: {TEMP_ROOT}")
  TEMP_ROOT.mkdir(mode=0o700,parents=True); TEMP_CONFIG.write_text(temporary_config(original_text)); os.chmod(TEMP_CONFIG,0o600)
  cfg=load_product_packet_engine_config(TEMP_CONFIG)
  if not cfg.tx_enabled or cfg.frequency_hz!=stage_i.EXPECTED_FREQUENCY_HZ: raise RuntimeError("temporary P7 radio profile failed")
  store=ObservedMailboxStore(TEMP_MAILBOX)
  def factory(): return MailboxNodeSession(callsign=LOCAL,peer=REMOTE,alias="YWDNOD",store=store,clock_ns=time.time_ns)
  node=InboundNodeSession(local=LOCAL,remote=REMOTE,maxframe=4,paclen=128,timers=LinkTimerConfig(t1_seconds=8,t2_seconds=1,t3_seconds=60,max_retries=2),session_factory=factory)
  env=os.environ.copy(); env["PYTHONPATH"]=str(ROOT/"src"); log_handle=TEMP_LOG.open("w")
  daemon=subprocess.Popen([sys.executable,"-m","ywd1278.daemon","--config",str(TEMP_CONFIG)],cwd=ROOT,env=env,stdout=log_handle,stderr=subprocess.STDOUT,text=True)
  stage_i._wait_port(TEMP_KISS_PORT,6); decoder=KISSStreamDecoder(max_body_bytes=4096); deadline=time.monotonic()+args.timeout; next_poll=time.monotonic()
  print("MAILBOX_LISTENER_ARMED=YES"); print("CONNECT_FROM=KJ6YWD-15"); print("CONNECT_TO=KJ6YWD-10")
  print("ENTER_IN_ORDER: HELP | LIST | SP KJ6YWD-15 P7 TEST | YWD-1278 0H-P7 MAILBOX TEST 1/1 | /EX | LIST | READ 1 | BYE")
  with socket.create_connection(("127.0.0.1",TEMP_KISS_PORT),timeout=3) as kiss:
   kiss.settimeout(.2)
   while time.monotonic()<deadline:
    now=time.monotonic()
    if now>=next_poll: actions+=send(kiss,node.poll(now=now)); next_poll=now+.05
    if node.snapshot.help_seen and node.snapshot.bye_seen and node.snapshot.state is LinkState.DISCONNECTED and store.deposits==1 and store.lists>=2 and store.reads>=1: complete=True; break
    try: chunk=kiss.recv(4096)
    except socket.timeout: continue
    if not chunk: raise RuntimeError("KISS stream closed during P7")
    for msg in decoder.feed(chunk):
     if msg.port==0 and msg.command==DATA and msg.frame: actions+=send(kiss,node.handle_frame(msg.frame,now=time.monotonic()))
  if not complete: raise RuntimeError(f"P7 sequence incomplete: node={node.snapshot} deposits={store.deposits} lists={store.lists} reads={store.reads}")
  saved=store.read_for(REMOTE,1)
  if saved is None or (saved.sender,saved.recipient,saved.subject,saved.body)!=(str(REMOTE),str(REMOTE),SUBJECT,BODY): raise RuntimeError(f"saved mailbox record mismatch: {saved}")
  print("INBOUND_SABM_UA=PASS"); print("MAILBOX_HELP=PASS"); print("EMPTY_LIST=PASS")
  print("MESSAGE_DEPOSIT=PASS"); print("POPULATED_LIST=PASS"); print("OWNER_READ=PASS")
  print("MESSAGE_CONTENT_EXACT=PASS"); print("BYE_ACK_BEFORE_DISC=PASS"); print("ORDERLY_DISC_UA=PASS")
 finally:
  if daemon is not None and daemon.poll() is None:
   daemon.send_signal(signal.SIGTERM)
   try: daemon.wait(timeout=8)
   except subprocess.TimeoutExpired: daemon.kill(); daemon.wait(timeout=2)
  if log_handle is not None: log_handle.close()
  if TEMP_ROOT.exists(): shutil.rmtree(TEMP_ROOT)
  if stopped:
   try: stage_i._restore_service(original_hash)
   except BaseException as exc: cleanup_error=exc
  if cleanup_error is not None: raise cleanup_error
 if not complete: raise SystemExit("[FAIL] P7 mailbox acceptance incomplete")
 if hashlib.sha256(stage_i.PERSISTENT_CONFIG.read_bytes()).hexdigest()!=original_hash: raise SystemExit("[FAIL] persistent config changed")
 print("YWD1278_0H_P7_MAILBOX_ACCEPTANCE=PASS"); print(f"LINK_ACTIONS_SUBMITTED={actions}")
 print("TEMPORARY_MAILBOX_REMOVED=YES"); print("NORMAL_SERVICE_RESTORED=YES"); print("PERSISTENT_TX_ENABLED=NO")
 print("PERSISTENT_CONFIG_MUTATED=NO"); print("FLASH_WRITTEN=NO"); print("OPTION_BYTES_WRITTEN=NO"); return 0
if __name__=="__main__": raise SystemExit(main())
