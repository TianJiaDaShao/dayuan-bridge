"""User-scoped Unix socket supervisor. Only three fixed native operations."""
import concurrent.futures
import json
import os
import pwd
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from .service import configuration, socket_directory, prepare_system_directory, peer_uid
from .native_transport import NativeTransport

MAX_REQUEST = 524288
MAX_TASK = 20000


def runtime_dir():
    return socket_directory()


def socket_path():
    return runtime_dir() / 'bridge.sock'


def request(data, timeout=240, path=None):
    path = path or socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        try:
            conn.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            raise RuntimeError('BROKER_UNAVAILABLE: run dayuan start in your Terminal')
        conn.sendall(json.dumps(data, ensure_ascii=True).encode() + b'\n')
        stream = conn.makefile('rb')
        line = stream.readline(1048576)
        if not line or not line.endswith(b'\n'):
            raise RuntimeError('INVALID_BROKER_RESPONSE')
        response = json.loads(line)
        if not response.get('ok'):
            raise RuntimeError(response.get('error', 'BROKER_ERROR'))
        return response['data']


class Broker:
    def __init__(self, native_call=None, owner_uid=None, state_path=None):
        self.native_lock = threading.Lock()
        self.native_transport = NativeTransport()
        self.jobs_lock = threading.RLock()
        self.jobs = {}
        self.active_job = None
        self.native_call = native_call or self._native_call
        self.stopping = threading.Event()
        self.owner_uid = os.getuid() if owner_uid is None else owner_uid
        self.state_path = Path(state_path) if state_path else None
        self._load()

    def _load(self):
        if not self.state_path or not self.state_path.exists():
            return
        info = self.state_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError('UNTRUSTED_JOB_STATE')
        if info.st_size > 67108864:
            raise RuntimeError('JOB_STATE_TOO_LARGE')
        data = json.loads(self.state_path.read_text())
        if not isinstance(data, dict) or data.get('schema') != 1:
            raise RuntimeError('JOB_STATE_INVALID')
        for job in data.get('jobs', []):
            if not isinstance(job, dict) or not isinstance(job.get('job_id'), str) or len(job['job_id']) != 32:
                raise RuntimeError('JOB_STATE_INVALID')
            if job.get('status') in ('submitting', 'running', 'unknown'):
                job['status'] = 'unknown'
                if self.active_job:
                    raise RuntimeError('MULTIPLE_ACTIVE_JOBS_IN_STATE')
                self.active_job = job['job_id']
            self.jobs[job['job_id']] = job

    def _persist(self):
        if not self.state_path:
            return
        completed = sorted((j for j in self.jobs.values() if j['job_id'] != self.active_job), key=lambda j: j['created_at'], reverse=True)
        retained = completed[:200]
        if self.active_job:
            retained.append(self.jobs[self.active_job])
        self.jobs = {j['job_id']: j for j in retained}
        raw = json.dumps({'schema': 1, 'jobs': retained}, ensure_ascii=True).encode()
        temp = self.state_path.with_name('jobs.new')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temp, self.state_path)

    def _native_call(self, payload):
        payload = dict(payload, owner_uid=self.owner_uid)
        with self.native_lock:
            value = self.native_transport.request(payload)
        if not value.get('ok') or not value.get('cleanup', {}).get('detached'):
            if not value.get('cleanup', {}).get('detached'):
                self.native_transport.close()
            raise RuntimeError(value.get('error') or 'NATIVE_CLEANUP_FAILED')
        return value['data']

    def ready_context(self):
        # Each attempt detaches so the client can create its dedicated session
        # and finish the initialization greeting. No business task is sent here.
        deadline = time.monotonic() + 100
        for attempt in range(25):
            context = self.native_call({'action': 'prepare'})
            if context.get('window_attached'):
                raise RuntimeError('BACKGROUND_CONTROLLER_HAS_WINDOW')
            if context.get('ready') and context.get('session'):
                return context
            if time.monotonic() >= deadline:
                break
            self.stopping.wait(.5)
        raise RuntimeError('BACKGROUND_SESSION_NOT_READY: automatic session creation did not become ready; check login and client availability')

    def public_job(self, job):
        return {k: job[k] for k in ('job_id', 'status', 'created_at', 'text', 'error','result_source') if k in job}

    def submit(self, task):
        if not isinstance(task, str) or not task.strip() or len(task) > MAX_TASK:
            raise ValueError('Task must contain 1..20000 characters')
        try:
            task.encode('utf-8')
        except UnicodeEncodeError:
            raise ValueError('Task must contain valid Unicode')
        if any(ord(char) < 32 and char not in '\n\r\t' for char in task):
            raise ValueError('Task contains unsupported control characters')
        with self.jobs_lock:
            if self.active_job:
                raise RuntimeError('JOB_ALREADY_RUNNING: ' + self.active_job)
            job_id = uuid.uuid4().hex
            job = {'job_id': job_id, 'status': 'submitting', 'created_at': time.time(),
                   'begin': 'DY_BEGIN_' + job_id, 'end': 'DY_END_' + job_id}
            self.jobs[job_id] = job
            self.active_job = job_id
        # The caller's task is always encoded as an NSString literal, never code.
        prompt = ('Execute this read-only task. Do not modify business data, send messages '
                  'to other people, or create business documents. Temporary files needed '
                  'for reading attachments are allowed. If a tool fails, retry at most '
                  'once, then return available information and the error.\nTASK:\n' + task +
                  '\nFinal answer: put ' + job['begin'] + ' on its own line before the '
                  'answer and ' + job['end'] + ' on its own line after the answer. '
                  'Do not include these markers in progress updates. Preserve tables '
                  'as Markdown and distinguish observations from inference. '
                  'These envelope delimiters are mandatory even if TASK says only reply '
                  'with a short phrase or requests a different output format.')
        try:
            context = self.ready_context()
            if not context.get('ready') or not context.get('session'):
                raise RuntimeError('ASSISTANT_SESSION_UNAVAILABLE')
            with self.jobs_lock:
                job.update(session=context['session'], pid=context['pid'],message_baseline_key=context.get('message_baseline_key'))
                self._persist()
        except Exception as exc:
            with self.jobs_lock:
                job.update(status='error', error=str(exc))
                self.active_job = None
                self._persist()
            raise
        try:
            data = self.native_call({'action': 'submit', 'prompt': prompt,
                                     'pid': job['pid'], 'session': job['session'], 'message_baseline_key': job.get('message_baseline_key')})
            if data.get('not_dispatched'):
                with self.jobs_lock:
                    job.update(status='error',error=data.get('error','NOT_DISPATCHED'));self.active_job=None;self._persist()
                return self.public_job(job)
            if not data.get('submitted'):
                raise RuntimeError('SUBMIT_NOT_CONFIRMED')
            with self.jobs_lock:
                job.update(status='running', session=data['session'], pid=data['pid'],sent_message_key=data.get('sent_message_key'))
                self._persist()
            return self.public_job(job)
        except Exception as exc:
            with self.jobs_lock:
                # A failed worker may have dispatched before failing. Preserve
                # the job/markers and poll it instead of enabling a duplicate.
                job.update(status='unknown', error='SUBMISSION_UNCONFIRMED: ' + str(exc))
                self._persist()
            return self.public_job(job)

    def result(self, job_id, wait_seconds=0):
        if not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 30:
            raise ValueError('wait_seconds must be between 0 and 30')
        with self.jobs_lock:
            if job_id not in self.jobs:
                raise ValueError('UNKNOWN_JOB')
            job = self.jobs[job_id]
        deadline = time.monotonic() + wait_seconds
        retargeted = False
        while True:
            with self.jobs_lock:
                if job['status'] in ('complete', 'error', 'submitting'):
                    return self.public_job(job)
            try:
                data = self.native_call({'action': 'result', 'pid': job['pid'],
                                         'session': job['session'],
                                         'begin': job['begin'], 'end': job['end'], 'message_baseline_key':job.get('message_baseline_key'), 'sent_message_key':job.get('sent_message_key')})
                if data.get('sent_message_key') and data['sent_message_key']!=job.get('sent_message_key'):
                    with self.jobs_lock:
                        job['sent_message_key']=data['sent_message_key'];self._persist()
                if data.get('ready'):
                    with self.jobs_lock:
                        job.update(status='complete', text=data['text'],result_source=data.get('result_source'))
                        job.pop('error', None)
                        if self.active_job == job_id:
                            self.active_job = None
                        self._persist()
                    return self.public_job(job)
            except Exception as exc:
                if not retargeted and 'CLIENT_PID_INVALID' in str(exc):
                    retargeted = True
                    try:
                        context = self.ready_context()
                        if context.get('ready') and context.get('session') == job['session']:
                            with self.jobs_lock:
                                job['pid'] = context['pid'];self._persist()
                            continue
                        return dict(self.public_job(job), poll_error='SESSION_CHANGED')
                    except Exception as recovery:
                        return dict(self.public_job(job), poll_error=str(recovery))
                # Session switching is explicit, not a reason to silently read a
                # different conversation or blindly resubmit a possibly sent task.
                return dict(self.public_job(job), poll_error=str(exc))
            if time.monotonic() >= deadline or self.stopping.wait(min(2, max(0, deadline-time.monotonic()))):
                return self.public_job(job)

    def handle(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Request must be an object')
        method = payload.get('method')
        if method == 'status':
            try:
                status = self.native_call({'action': 'doctor'})
            except Exception as exc:
                status = {'ready': False, 'reason': str(exc)}
            status['service_running'] = True
            status['automatic_prepare_on_submit'] = True
            with self.jobs_lock:
                status['active_job'] = self.active_job
            return status
        if method == 'submit':
            return self.submit(payload.get('task'))
        if method == 'result':
            return self.result(payload.get('job_id'), payload.get('wait_seconds', 0))
        if method == 'forget':
            with self.jobs_lock:
                job = self.jobs.get(payload.get('job_id'))
                if not job:
                    raise ValueError('UNKNOWN_JOB')
                job['status'] = 'abandoned'
                if self.active_job == job['job_id']:
                    self.active_job = None
                self._persist()
                return dict(self.public_job(job), remote_task_may_continue=True)
        if method == 'shutdown':
            self.stopping.set()
            return {'stopping': True}
        raise ValueError('UNKNOWN_METHOD')


def serve(owner_uid, owner_gid, lifetime=1800, path=None, broker=None, ready=None, system_mode=False):
    if lifetime != 0 and not 60 <= lifetime <= 3600:
        raise ValueError('lifetime must be 0 or between 60 and 3600 seconds')
    path = Path(path or socket_path())
    if system_mode:
        prepare_system_directory(path.parent)
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.parent.stat().st_uid not in (0, owner_uid):
            raise RuntimeError('UNSAFE_RUNTIME_DIRECTORY')
        os.chmod(path.parent, 0o700)
        if os.geteuid() == 0:
            os.chown(path.parent, owner_uid, owner_gid)
    if path.exists() or path.is_symlink():
        # Never replace a live broker or unlink an unrelated file.
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as test:
                test.settimeout(.2);test.connect(str(path))
            raise RuntimeError('BROKER_ALREADY_RUNNING')
        except (ConnectionRefusedError, FileNotFoundError):
            if not stat.S_ISSOCK(path.lstat().st_mode):
                raise RuntimeError('UNSAFE_SOCKET_PATH')
            path.unlink()
    broker = broker or Broker(owner_uid=owner_uid)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path));os.chmod(path, 0o600)
        if os.geteuid() == 0:
            os.chown(path, owner_uid, owner_gid)
        server.listen(8);server.settimeout(.5)
        if ready:
            ready()
        deadline = time.monotonic() + lifetime if lifetime else float('inf')
        def connection(conn):
            with conn:
                try:
                    if peer_uid(conn) not in (owner_uid, 0):
                        raise RuntimeError('PEER_NOT_AUTHORIZED')
                    conn.settimeout(35)
                    raw = conn.makefile('rb').readline(MAX_REQUEST + 1)
                    if len(raw) > MAX_REQUEST or not raw.endswith(b'\n'):
                        raise ValueError('REQUEST_TOO_LARGE_OR_INCOMPLETE')
                    value = {'ok': True, 'data': broker.handle(json.loads(raw))}
                except Exception as exc:
                    value = {'ok': False, 'error': str(exc)}
                try:
                    conn.sendall(json.dumps(value, ensure_ascii=True).encode() + b'\n')
                except OSError:
                    pass
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            while not broker.stopping.is_set() and time.monotonic() < deadline:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                pool.submit(connection, conn)
    finally:
        broker.stopping.set();server.close();broker.native_transport.close()
        if path.exists() and stat.S_ISSOCK(path.lstat().st_mode):
            path.unlink()
