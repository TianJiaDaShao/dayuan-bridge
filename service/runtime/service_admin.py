"""Fixed service administration commands. No arbitrary command endpoint."""
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dayuan.service import ROOT, CONFIG, LABEL, configuration

PLIST = Path('/Library/LaunchDaemons') / (LABEL + '.plist')

def call(args, check=True):
    return subprocess.run(args, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)

def main():
    if os.geteuid()!=0 or len(sys.argv)!=2:
        raise RuntimeError('Administrator authorization is required')
    action=sys.argv[1]
    if action not in ('start','stop','restart','uninstall'):
        raise RuntimeError('Unknown action')
    config=configuration()
    if not config:
        raise RuntimeError('Service configuration is missing')
    loaded=call(['/bin/launchctl','print','system/'+LABEL],False).returncode==0
    if action in ('stop','restart','uninstall') and loaded:
        call(['/bin/launchctl','bootout','system/'+LABEL])
    if action in ('start','restart'):
        if action=='start' and loaded:
            call(['/bin/launchctl','kickstart','system/'+LABEL])
        else:
            for attempt in range(20):
                result=call(['/bin/launchctl','bootstrap','system',str(PLIST)],False)
                if result.returncode==0:break
                time.sleep(.5)
            else:raise RuntimeError('launchd bootstrap failed: '+result.stderr)
        print('Dayuan Bridge service started')
    if action=='stop':print('Dayuan Bridge service stopped')
    if action=='uninstall':
        user=pwd.getpwuid(config['owner_uid']).pw_name
        call(['/usr/bin/sudo','-H','-u',user,'/usr/bin/python3','-I',str(ROOT/'integrate_user.py'),'remove'],False)
        link=Path('/usr/local/bin/dayuan')
        if link.is_symlink() and os.readlink(link)==str(ROOT/'dayuan-cli'):link.unlink()
        if PLIST.exists():PLIST.unlink()
        runtime=Path('/var/run/dayuan-bridge')/str(config['owner_uid'])
        if runtime.exists() and not runtime.is_symlink():shutil.rmtree(runtime)
        if ROOT.is_symlink():raise RuntimeError('Unexpected installation symlink')
        shutil.rmtree(ROOT)
        call(['/usr/sbin/pkgutil','--forget',LABEL],False)
        print('Uninstalled. Local job history is retained in /var/db/dayuan-bridge.')

if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);raise SystemExit(1)
