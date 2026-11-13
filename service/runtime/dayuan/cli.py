import argparse
import json
import os
import pwd
from pathlib import Path
import signal
import sys
import time
from . import __version__
from .broker import Broker, request, serve
from .service import configuration, admin, prepare_system_directory


def main(argv=None):
    parser = argparse.ArgumentParser(prog='dayuan')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    server = sub.add_parser('serve', help='Start private broker; run once using sudo.')
    server.add_argument('--lifetime', type=int, default=1800)
    server.add_argument('--system-service', action='store_true')
    start = sub.add_parser('start', help='Start broker in your Terminal, authenticating once using sudo.')
    sub.add_parser('status', help='Check existing assistant session without UI calibration.')
    submit = sub.add_parser('submit', help='Submit one read-only task; returns job ID.')
    submit.add_argument('task')
    result = sub.add_parser('result', help='Retrieve an existing task without resubmitting.')
    result.add_argument('job_id');result.add_argument('--wait', type=float, default=0)
    ask = sub.add_parser('ask', help='Submit once and poll; timeouts preserve the job ID.')
    ask.add_argument('task');ask.add_argument('--timeout', type=float, default=600)
    ask.add_argument('--output', type=Path)
    sub.add_parser('shutdown', help='Stop broker; does not cancel tasks already running in Dayuan.')
    service = sub.add_parser('service', help='Manage installed macOS background service.')
    service.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'uninstall'])
    forget = sub.add_parser('forget', help='Stop tracking a task; does not cancel it remotely.')
    forget.add_argument('job_id')
    args = parser.parse_args(argv)
    try:
        if args.command == 'start':
            if not configuration():
                raise RuntimeError('SERVICE_NOT_INSTALLED: install the Dayuan Bridge package first')
            admin('start')
        if args.command == 'service':
            if args.action in ('start', 'restart', 'uninstall'):
                admin(args.action)
            if args.action == 'stop':
                print(json.dumps(request({'method': 'shutdown'})));return 0
            args.command = 'status'
        if args.command == 'serve':
            config = configuration()
            if os.geteuid() != 0 or not args.system_service or not config:
                raise RuntimeError('Use the installed launchd service')
            uid = config['owner_uid'];gid = pwd.getpwuid(uid).pw_gid
            directory = Path('/var/db/dayuan-bridge') / str(uid)
            prepare_system_directory(directory)
            broker = Broker(owner_uid=uid, state_path=directory/'jobs.json')
            def stop(signum, frame):
                broker.stopping.set()
            signal.signal(signal.SIGINT, stop);signal.signal(signal.SIGTERM, stop)
            serve(uid, gid, lifetime=0, broker=broker, system_mode=True,
                  ready=lambda: print('DAYUAN_BRIDGE_READY', flush=True))
            print('DAYUAN_BRIDGE_STOPPED', flush=True)
            return 0
        if args.command == 'status':
            data = request({'method': 'status'})
        elif args.command == 'submit':
            data = request({'method': 'submit', 'task': args.task})
        elif args.command == 'result':
            data = request({'method': 'result', 'job_id': args.job_id, 'wait_seconds': args.wait}, timeout=180)
        elif args.command == 'shutdown':
            data = request({'method': 'shutdown'})
        elif args.command == 'forget':
            data = request({'method': 'forget', 'job_id': args.job_id})
        else:
            if not 1 <= args.timeout <= 3600:
                raise ValueError('timeout must be between 1 and 3600 seconds')
            data = request({'method': 'submit', 'task': args.task})
            print(json.dumps({'job_id': data['job_id'], 'status': data['status']}, ensure_ascii=True), file=sys.stderr, flush=True)
            deadline = time.monotonic() + args.timeout
            while data['status'] not in ('complete', 'error') and time.monotonic() < deadline:
                data = request({'method': 'result', 'job_id': data['job_id'], 'wait_seconds': min(20, max(0, deadline-time.monotonic()))}, timeout=180)
                if data.get('poll_error'):
                    break
            if data['status'] == 'complete' and args.output:
                tmp = args.output.with_name(args.output.name + '.tmp')
                with tmp.open('w', encoding='utf-8') as out:
                    os.chmod(tmp, 0o600);out.write(data['text'] + '\n')
                os.replace(tmp, args.output)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if data.get('status') == 'error':
            return 1
        if args.command == 'ask' and data.get('status') != 'complete':
            return 2
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
