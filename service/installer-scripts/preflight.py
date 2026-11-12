import json,os,platform,plistlib,socket,stat,subprocess
from pathlib import Path
root=Path('/Library/Application Support/Dayuan Bridge')
if platform.machine()!='arm64':raise SystemExit('This preview supports Apple silicon Macs only.')
uid=os.stat('/dev/console').st_uid
if uid<501:raise SystemExit('Log into the Mac with a regular user before installing.')
if root.exists() or root.is_symlink():
 info=root.lstat()
 if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise SystemExit('Untrusted existing installation directory.')
link=Path('/usr/local/bin/dayuan')
if link.exists() or link.is_symlink():
 if not link.is_symlink() or os.readlink(link)!=str(root/'dayuan-cli'):raise SystemExit('/usr/local/bin/dayuan already belongs to another installation.')
subprocess.run(['/usr/bin/python3','-I','-c','import sys;sys.path.insert(0,"/Library/Developer/CommandLineTools/Library/PrivateFrameworks/LLDB.framework/Resources/Python");import lldb'],check=True)
p=Path('/Applications/\u4f01\u4e1a\u5fae\u4fe1.app/Contents/Info.plist')
if not p.exists():raise SystemExit('Install Enterprise WeChat first.')
with p.open('rb') as f:d=plistlib.load(f)
if (d.get('CFBundleShortVersionString'),d.get('CFBundleVersion'))!=('5.0.13','70807'):raise SystemExit('This build is validated for WeCom 5.0.13 (70807).')
config=root/'service.json'
if config.exists():
 info=config.lstat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise SystemExit('Untrusted service configuration.')
 owner=json.loads(config.read_text())['owner_uid']
 path=Path('/var/run/dayuan-bridge')/str(owner)/'bridge.sock'
 if path.exists():
  try:
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
    conn.settimeout(20);conn.connect(str(path));conn.sendall(b'{"method":"status"}\n');data=json.loads(conn.makefile('rb').readline(1048576))
   if data.get('data',{}).get('active_job'):raise SystemExit('A task is active. Retrieve or forget it before upgrading.')
  except (ConnectionRefusedError,FileNotFoundError):pass
print('Dayuan Bridge preflight passed.')
