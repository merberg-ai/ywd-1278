#!/usr/bin/env python3
"""Guarded 0H-P5 physical inbound node acceptance from KJ6YWD-5."""
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
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402

EXPECTED_HOST_COMMIT="b666ad2eeb144c30b1e1eee542f0eb2a1983bd85"
AUTHORIZATION_TOKEN="0H-P5-INBOUND-NODE-145050-KJ6YWD15-ONE"
ARM_PHRASE="TRANSMIT-0H-P5-INBOUND-NODE-KJ6YWD-15-ONE"
TEMP_ROOT=Path("/run/ywd-1278-0h-p5"); TEMP_CONFIG=TEMP_ROOT/"config.toml"
TEMP_LOG=TEMP_ROOT/"daemon.log"; TEMP_PTY=str(TEMP_ROOT/"tnc")
TEMP_KISS_PORT=18401; TEMP_CONSOLE_PORT=18410
LOCAL=Address.parse("KJ6YWD-10"); REMOTE=Address.parse("KJ6YWD-15")

def make_temporary_tx_config(original:str)->str:
 text=stage_i.replace_toml_key(original,"radio","tx_power",str(stage_i.TX_POWER))
 text=stage_i.replace_toml_key(text,"radio","tx_enabled","true")
 text=stage_i.replace_toml_key(text,"kiss","port",str(TEMP_KISS_PORT))
 text=stage_i.replace_toml_key(text,"console","port",str(TEMP_CONSOLE_PORT))
 return stage_i.replace_toml_key(text,"console","pty_link",f'"{TEMP_PTY}"')

def print_plan()->None:
 print("===== YWD-1278 0H-P5 INBOUND NODE ACCEPTANCE =====")
 print(f"HOST_BASE_CHECKPOINT={EXPECTED_HOST_COMMIT}"); print(f"LOCAL_NODE={LOCAL}")
 print("LOCAL_ALIAS=YWDNOD"); print(f"EXPECTED_REMOTE={REMOTE}")
 print("REQUIRED_COMMANDS=HELP,INFO,BYE"); print("TX_FREQUENCY_HZ=145050000")
 print("TX_POWER=200"); print("CONCURRENT_INBOUND_SESSIONS_MAX=1")
 print("REMOTE_PEER_FILTER=EXACT"); print("BYE_ACK_BEFORE_DISC=REQUIRED")
 print("PERSISTENT_CONFIG_MUTATED=NO"); print("FLASH_WRITTEN=NO")
 print("OPTION_BYTES_WRITTEN=NO")

def send_actions(sock:socket.socket,result)->int:
 for action in result.actions: sock.sendall(encode(action.frame_no_fcs,port=0,command=DATA))
 return len(result.actions)

def main()->int:
 ap=argparse.ArgumentParser(description="0H-P5 guarded inbound-node RF acceptance")
 ap.add_argument("--transmit",action="store_true"); ap.add_argument("--authorize",default="")
 ap.add_argument("--firmware",type=Path); ap.add_argument("--timeout",type=float,default=180.0)
 args=ap.parse_args(); print_plan()
 if not args.transmit:
  print("YWD1278_0H_P5_DRY_RUN=PASS"); print("SERVICE_MUTATED=NO")
  print("MODEM_UART_OPENED=NO"); print("RF_TRANSMITTED=NO"); return 0
 if os.geteuid()!=0: raise SystemExit("[FAIL] physical P5 requires root")
 if args.authorize!=AUTHORIZATION_TOKEN: raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
 if args.firmware is None: raise SystemExit("[FAIL] --firmware is required")
 if not 30<=args.timeout<=300: raise SystemExit("[FAIL] --timeout must be 30..300 seconds")
 if stage_i._run(["git","merge-base","--is-ancestor",EXPECTED_HOST_COMMIT,"HEAD"],check=False).returncode!=0:
  raise SystemExit("[FAIL] checkout does not descend from the P4 checkpoint")
 for path in (stage_i.PERSISTENT_CONFIG,stage_i.INSTALLED_COMMIT,stage_i.VENV_PYTHON,stage_i.ELIGIBILITY):
  if not path.exists(): raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
 if stage_i._systemctl_state("is-enabled")!="enabled" or stage_i._systemctl_state("is-active")!="active":
  raise SystemExit("[FAIL] normal appliance must be enabled and active")
 original_bytes=stage_i.PERSISTENT_CONFIG.read_bytes(); original_hash=hashlib.sha256(original_bytes).hexdigest()
 original_text=original_bytes.decode("utf-8"); source=stage_i.validate_persistent_config(tomllib.loads(original_text))
 if source!=str(LOCAL): raise SystemExit(f"[FAIL] configured station must be {LOCAL}; actual={source}")
 stage_i._check_firmware(args.firmware); stage_i._verify_eligibility(args.firmware)
 print(f"PERSISTENT_CONFIG_SHA256={original_hash}"); print("PERSISTENT_TX_ENABLED=NO")
 typed=input(f"Type exactly {ARM_PHRASE} to accept ONE inbound RF node session: ").strip()
 if typed!=ARM_PHRASE: raise SystemExit("[FAIL] P5 interactive arm phrase did not match")
 daemon=None; log_handle=None; service_stopped=False; completed=False; total_actions=0; cleanup_error=None
 try:
  stage_i._run(["systemctl","stop",stage_i.SERVICE]); service_stopped=True
  if stage_i._run(["fuser",stage_i.DEVICE],check=False).returncode==0: raise RuntimeError("UART remained owned after normal service stop")
  stage_i._verify_hardware_identity()
  if TEMP_ROOT.exists(): raise RuntimeError(f"stale P5 runtime directory exists: {TEMP_ROOT}")
  TEMP_ROOT.mkdir(mode=0o700,parents=True); TEMP_CONFIG.write_text(make_temporary_tx_config(original_text),encoding="utf-8")
  os.chmod(TEMP_CONFIG,0o600); cfg=load_product_packet_engine_config(TEMP_CONFIG)
  if not cfg.tx_enabled or cfg.frequency_hz!=stage_i.EXPECTED_FREQUENCY_HZ: raise RuntimeError("temporary P5 radio profile failed validation")
  env=os.environ.copy(); env["PYTHONPATH"]=str(ROOT/"src"); log_handle=TEMP_LOG.open("w",encoding="utf-8")
  daemon=subprocess.Popen([sys.executable,"-m","ywd1278.daemon","--config",str(TEMP_CONFIG)],cwd=str(ROOT),env=env,stdout=log_handle,stderr=subprocess.STDOUT,text=True)
  stage_i._wait_port(TEMP_KISS_PORT,6.0)
  node=InboundNodeSession(local=LOCAL,remote=REMOTE,maxframe=4,paclen=128,timers=LinkTimerConfig(t1_seconds=8,t2_seconds=1,t3_seconds=60,max_retries=2))
  decoder=KISSStreamDecoder(max_body_bytes=4096); deadline=time.monotonic()+args.timeout; next_poll=time.monotonic()
  print("INBOUND_LISTENER_ARMED=YES"); print(f"NOW_CONNECT_FROM={REMOTE}"); print(f"CONNECT_TO={LOCAL}")
  with socket.create_connection(("127.0.0.1",TEMP_KISS_PORT),timeout=3) as kiss:
   kiss.settimeout(.2)
   while time.monotonic()<deadline:
    now=time.monotonic()
    if now>=next_poll:
     total_actions+=send_actions(kiss,node.poll(now=now)); next_poll=now+.05
    snap=node.snapshot
    if snap.connections==1 and snap.help_seen and snap.info_seen and snap.bye_seen and snap.state is LinkState.DISCONNECTED:
     completed=True; break
    try: chunk=kiss.recv(4096)
    except socket.timeout: continue
    if not chunk: raise RuntimeError("KISS stream closed during inbound-node acceptance")
    for message in decoder.feed(chunk):
     if message.port!=0 or message.command!=DATA or not message.frame: continue
     total_actions+=send_actions(kiss,node.handle_frame(message.frame,now=time.monotonic()))
  snap=node.snapshot
  if not completed: raise RuntimeError(f"timed out waiting for HELP, INFO, BYE and orderly release; state={snap}")
  print("INBOUND_SABM_UA=PASS"); print("NODE_BANNER_SENT=PASS")
  print("NODE_HELP=PASS"); print("NODE_INFO=PASS"); print("NODE_BYE=PASS")
  print("BYE_ACK_BEFORE_DISC=PASS"); print("ORDERLY_DISC_UA=PASS")
 finally:
  if daemon is not None and daemon.poll() is None:
   daemon.send_signal(signal.SIGTERM)
   try: daemon.wait(timeout=8)
   except subprocess.TimeoutExpired: daemon.kill(); daemon.wait(timeout=2)
  if log_handle is not None: log_handle.close()
  if TEMP_ROOT.exists(): shutil.rmtree(TEMP_ROOT)
  if service_stopped:
   try: stage_i._restore_service(original_hash)
   except BaseException as exc: cleanup_error=exc
  if cleanup_error is not None: raise cleanup_error
 if not completed: raise SystemExit("[FAIL] inbound-node acceptance did not complete")
 if hashlib.sha256(stage_i.PERSISTENT_CONFIG.read_bytes()).hexdigest()!=original_hash: raise SystemExit("[FAIL] persistent config changed during P5")
 print("YWD1278_0H_P5_INBOUND_NODE_ACCEPTANCE=PASS"); print(f"LINK_ACTIONS_SUBMITTED={total_actions}")
 print("NORMAL_SERVICE_RESTORED=YES"); print("PERSISTENT_TX_ENABLED=NO")
 print("PERSISTENT_CONFIG_MUTATED=NO"); print("FLASH_WRITTEN=NO"); print("OPTION_BYTES_WRITTEN=NO")
 return 0
if __name__=="__main__": raise SystemExit(main())
