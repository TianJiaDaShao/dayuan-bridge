"""System-service configuration and authenticated local peer identity."""
import ctypes
import json
import os
from pathlib import Path
import pwd
import stat

ROOT = Path('/Library/Application Support/Dayuan Bridge')
CONFIG = ROOT / 'service.json'
LABEL = 'local.dayuan.bridge'


def configuration():
    if not CONFIG.exists():
        return None
    info = CONFIG.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('UNTRUSTED_SERVICE_CONFIGURATION')
    data = json.loads(CONFIG.read_text())
    uid = data.get('owner_uid')
    if type(uid) is not int or uid < 501:
        raise RuntimeError('INVALID_SERVICE_OWNER')
    pwd.getpwuid(uid)
    return data


def socket_directory():
    config = configuration()
    if config:
        if os.geteuid() != 0 and os.getuid() != config['owner_uid']:
            raise RuntimeError('SERVICE_BELONGS_TO_ANOTHER_USER')
        return Path('/var/run/dayuan-bridge') / str(config['owner_uid'])
    uid = int(os.environ.get('SUDO_UID', os.getuid())) if os.geteuid() == 0 else os.getuid()
    return Path(pwd.getpwuid(uid).pw_dir) / 'Library' / 'Application Support' / 'dayuan-local'


def peer_uid(conn):
    if hasattr(conn, 'getpeereid'):
        return conn.getpeereid()[0]
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.getpeereid
    fn.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    fn.restype = ctypes.c_int
    uid, gid = ctypes.c_uint(), ctypes.c_uint()
    if fn(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
        raise OSError(ctypes.get_errno(), 'getpeereid failed')
    return uid.value


def prepare_system_directory(directory):
    """Fixed root-owned directories; never chmod/chown a user-controlled path."""
    directory = Path(directory)
    allowed = [Path('/var/run/dayuan-bridge'), Path('/var/db/dayuan-bridge')]
    if directory.parent not in allowed:
        raise RuntimeError('INVALID_SYSTEM_DIRECTORY')
    for path in [directory.parent, directory]:
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('UNTRUSTED_SYSTEM_DIRECTORY')
        else:
            path.mkdir(mode=0o711)
        os.chmod(path, 0o711 if str(path).startswith('/var/run/') else 0o700)


def admin(action):
    if action not in ('start', 'stop', 'restart', 'uninstall'):
        raise ValueError('UNKNOWN_SERVICE_ACTION')
    helper = ROOT / 'service_admin.py'
    os.execvp('sudo', ['sudo', '/usr/bin/python3', '-I', str(helper), action])
