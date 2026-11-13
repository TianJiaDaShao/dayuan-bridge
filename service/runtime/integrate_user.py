"""Runs as the ordinary owning user, never as root."""
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path('/Library/Application Support/Dayuan Bridge')
COMMAND=str(ROOT/'dayuan-cli')

def legacy_shutdown():
    old=Path.home()/'Library/Application Support/dayuan-local/bridge.sock'
    if not old.exists():return
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.settimeout(20);conn.connect(str(old));conn.sendall(b'{"method":"status"}\n')
            data=json.loads(conn.makefile('rb').readline(1048576))
        if data.get('data',{}).get('active_job'):return
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.settimeout(10);conn.connect(str(old));conn.sendall(b'{"method":"shutdown"}\n');conn.recv(4096)
    except (OSError,ValueError):pass

def main():
    if os.geteuid()==0:raise RuntimeError('User integration must not run as root')
    action=sys.argv[1]
    directory=Path.home()/'.local/bin';link=directory/'dayuan'
    legacy=str(Path.home()/'.local/share/dayuan-local/dayuan-cli')
    if action=='install':
        legacy_shutdown();directory.mkdir(parents=True,exist_ok=True)
        if not link.exists() and not link.is_symlink():link.symlink_to(COMMAND)
        elif link.is_symlink() and os.readlink(link) in (legacy,COMMAND):
            temp=directory/'.dayuan-new'
            if temp.is_symlink():temp.unlink()
            if temp.exists():raise RuntimeError('Unexpected temporary CLI file')
            temp.symlink_to(COMMAND);os.replace(temp,link)
    elif action=='remove':
        if link.is_symlink() and os.readlink(link)==COMMAND:link.unlink()
    else:raise RuntimeError('Unknown integration action')

if __name__=='__main__':main()
