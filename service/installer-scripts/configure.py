import json,os,plistlib,pwd,stat,subprocess,time
from pathlib import Path
root=Path('/Library/Application Support/Dayuan Bridge');config=root/'service.json'
if root.is_symlink() or root.stat().st_uid!=0:raise SystemExit('Invalid installation ownership')
uid=os.stat('/dev/console').st_uid
if config.exists():
 info=config.lstat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise SystemExit('Untrusted existing service configuration')
 uid=json.loads(config.read_text())['owner_uid']
if type(uid) is not int or uid<501:raise SystemExit('A logged-in regular user is required')
account=pwd.getpwuid(uid)
temp=root/'service.new'
fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o644)
with os.fdopen(fd,'w') as stream:json.dump({'schema':1,'owner_uid':uid,'version':'0.2.1'},stream);stream.write('\n')
os.replace(temp,config);os.chown(config,0,0);os.chmod(config,0o644)
for directory,dirs,files in os.walk(root,followlinks=False):
 os.chown(directory,0,0);os.chmod(directory,0o755)
 for name in files:
  p=Path(directory)/name
  if p.is_symlink():raise SystemExit('Unexpected payload symlink')
  os.chown(p,0,0);os.chmod(p,0o755 if name=='dayuan-cli' else 0o644)
# Retire files shipped by the former protocol adapter.
for obsolete in (root/'dayuan/mcp.py', root/'mcp-config.json'):
 if obsolete.is_file() or obsolete.is_symlink():obsolete.unlink()
log=Path('/var/log/dayuan-bridge');log.mkdir(mode=0o700,exist_ok=True)
if log.is_symlink() or log.stat().st_uid!=0:raise SystemExit('Untrusted log directory')
os.chmod(log,0o700)
for name in ('service.log','service-error.log'):
 fd=os.open(log/name,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600);os.close(fd)
# User integration has no root authority, including when touching ~/.codex.
integration=subprocess.run(['/bin/launchctl','asuser',str(uid),'/usr/bin/sudo','-H','-u',account.pw_name,'/usr/bin/python3','-I',str(root/'integrate_user.py'),'install'],capture_output=True,text=True,timeout=60)
if integration.returncode:print('Optional user integration needs attention; the system CLI is /usr/local/bin/dayuan.')
plist=Path('/Library/LaunchDaemons/local.dayuan.bridge.plist');os.chown(plist,0,0);os.chmod(plist,0o644)
subprocess.run(['/bin/launchctl','bootstrap','system',str(plist)],check=True)
print('Dayuan Bridge installed and started for uid',uid)
