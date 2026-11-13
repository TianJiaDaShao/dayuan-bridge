"""Isolated native worker; stdin/stdout are a single JSON request/response."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

LLDB_PYTHON = '/Library/Developer/CommandLineTools/Library/PrivateFrameworks/LLDB.framework/Resources/Python'
sys.path.insert(0, LLDB_PYTHON)
import lldb
from . import native

EXE = '/Applications/\u4f01\u4e1a\u5fae\u4fe1.app/Contents/MacOS/\u4f01\u4e1a\u5fae\u4fe1'


class BridgeError(Exception):
    pass


def find_pid(requested=None, owner_uid=None):
    if type(owner_uid) is not int or owner_uid < 501:
        raise BridgeError('OWNER_UID_REQUIRED')
    listing = subprocess.check_output(['/bin/ps', '-axo', 'uid=,pid=,command='], text=True)
    candidates = []
    for line in listing.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and int(parts[0]) == owner_uid and parts[2] == EXE:
            candidates.append(int(parts[1]))
    if requested is not None:
        if requested not in candidates:
            raise BridgeError('CLIENT_PID_INVALID')
        return requested
    if not candidates:
        raise BridgeError('CLIENT_NOT_RUNNING')
    return min(candidates)


class NativeSession:
    def __init__(self, pid=None, fixture=None, owner_uid=None, cached=None):
        self.process = None
        self.client_version = {'version': 'fixture', 'build': 'fixture'}
        if not fixture:
            with (Path(EXE).parents[1] / 'Info.plist').open('rb') as stream:
                metadata = plistlib.load(stream)
            self.client_version = {'version': metadata.get('CFBundleShortVersionString'),
                                   'build': metadata.get('CFBundleVersion')}
            if self.client_version != {'version': '5.0.13', 'build': '70807'}:
                raise BridgeError('CLIENT_VERSION_UNVERIFIED: refusing native calls until compatibility is checked')
        self.debugger = cached[0] if cached else lldb.SBDebugger.Create(False)
        self.debugger.SetAsync(False)
        self.target = cached[1] if cached else self.debugger.CreateTarget(str(fixture) if fixture else None)
        self.listener = lldb.SBListener('dayuan-native-worker')
        error = lldb.SBError()
        if fixture:
            bp = self.target.BreakpointCreateByName('fixture_ready')
            info = lldb.SBLaunchInfo([])
            info.SetListener(self.listener)
            self.process = self.target.Launch(info, error)
            self.fixture = True
            self.target.DeleteAllBreakpoints()
        else:
            self.fixture = False
            self.pid = find_pid(pid, owner_uid)
            self.process = self.target.AttachToProcessWithID(self.listener, self.pid, error)
        if error.Fail():
            raise BridgeError('ATTACH_FAILED: ' + str(error))
        if self.process.GetState() != lldb.eStateStopped:
            raise BridgeError('CLIENT_NOT_STOPPED')
        self.pid = self.process.GetProcessID()
        self.thread = self.process.GetThreadAtIndex(0)
        for thread in self.process:
            if thread.GetIndexID() == 1:
                self.thread = thread
                break
        self.frame = self.thread.GetFrameAtIndex(0)

    def number(self, expression):
        options = lldb.SBExpressionOptions()
        options.SetLanguage(lldb.eLanguageTypeObjC_plus_plus)
        options.SetIgnoreBreakpoints(True)
        options.SetUnwindOnError(True)
        options.SetTimeoutInMicroSeconds(3000000)
        value = self.frame.EvaluateExpression(expression, options)
        if value.GetError().Fail():
            raise BridgeError('NATIVE_EXPRESSION_FAILED: ' + str(value.GetError()))
        return value.GetValueAsUnsigned()

    def string(self, expression):
        ptr = self.number(expression)
        if not ptr:
            return None
        error = lldb.SBError()
        result = self.process.ReadCStringFromMemory(ptr, 262144, error)
        if error.Fail():
            raise BridgeError('RESULT_READ_FAILED')
        return result

    def doctor(self):
        mask = self.number(native.doctor_expression())
        stages = ['class', 'assistant', 'conversation', 'view', 'sender', 'messages']
        return {'pid': self.pid, 'ready': mask == 63, 'client': self.client_version,
                'components': {name: bool(mask & (1 << i)) for i, name in enumerate(stages)}}

    def session_id(self):
        return self.string(native.session_expression())

    def handle(self, request):
        action = request['action']
        if action == 'prepare':
            self.number(native.prepare_expression())
            status = self.doctor()
            if status['ready']:
                status['session_bootstrap_complete'] = bool(self.number(native.bootstrap_ready_expression()))
                status['ready'] = status['session_bootstrap_complete']
            status['session'] = self.session_id() if status['ready'] else None
            status['window_attached'] = bool(self.number(native.window_expression()))
            return status
        status = self.doctor()
        if action == 'doctor':
            status['session'] = self.session_id() if status['ready'] else None
            return status
        if not status['ready']:
            raise BridgeError('ASSISTANT_SESSION_UNAVAILABLE')
        session = self.session_id()
        if request.get('session') and request['session'] != session:
            raise BridgeError('SESSION_CHANGED')
        if action == 'submit':
            if self.number(native.submit_expression(request['prompt'])) != 1:
                raise BridgeError('SUBMIT_UNAVAILABLE')
            return {'submitted': True, 'pid': self.pid, 'session': session}
        if action == 'result':
            begin, end = request['begin'], request['end']
            text = self.string(native.result_expression(begin, end))
            if text is None:
                return {'ready': False, 'session': session}
            start = text.find(begin)
            finish = text.rfind(end)
            if start < 0 or finish <= start:
                raise BridgeError('INCOMPLETE_RESULT')
            return {'ready': True, 'session': session, 'text': text[start + len(begin):finish].strip()}
        raise BridgeError('UNKNOWN_NATIVE_ACTION')

    def close(self):
        if not self.process or not self.process.IsValid():
            return {'detached': True}
        # Never Continue before Detach: this worker operates on a stopped target
        # throughout. Detach itself resumes it and restores debugger state.
        self.target.DeleteAllBreakpoints()
        error = self.process.Detach()
        if error.Fail():
            raise BridgeError('DETACH_FAILED: ' + str(error))
        return {'detached': True}


def execute(request, fixture=None, cached=None):
    response = {}; session = None; code = 0
    try:
        if request.get('action') not in ('doctor', 'prepare', 'submit', 'result'):
            raise BridgeError('UNKNOWN_NATIVE_ACTION')
        session = NativeSession(request.get('pid'), fixture, request.get('owner_uid'), cached)
        response = {'ok': True, 'data': session.handle(request)}
    except Exception as exc:
        response = {'ok': False, 'error': str(exc)}
        code = 1
    finally:
        if session:
            try:
                response['cleanup'] = session.close()
            except Exception as exc:
                response['cleanup'] = {'detached': False, 'error': str(exc)}
                response['ok'] = False
                code = 1
    return response, code


def main():
    lldb.SBDebugger.Initialize()
    if sys.argv[1:] == ['--persistent']:
        debugger = lldb.SBDebugger.Create(False)
        debugger.SetAsync(False)
        target = None; target_pid = None
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if not isinstance(request, dict):raise ValueError('INVALID_NATIVE_REQUEST')
                if request.get('action') not in ('doctor','prepare','submit','result'):raise BridgeError('UNKNOWN_NATIVE_ACTION')
                pid = find_pid(request.get('pid'), request.get('owner_uid'))
                if target is None or pid != target_pid:
                    target = debugger.CreateTarget(None); target_pid = pid
                response, code = execute(request, cached=(debugger, target))
            except Exception as exc:
                response = {'ok': False, 'error': str(exc)}
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + '\n');sys.stdout.flush()
        os._exit(0)
    fixture = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == '--fixture' else None
    try:
        response, code = execute(json.load(sys.stdin), fixture=fixture)
    except Exception as exc:
        response, code = {'ok':False, 'error':str(exc)}, 1
    sys.stdout.write(json.dumps(response, ensure_ascii=True) + '\n');sys.stdout.flush()
    # Each request explicitly detaches; skip LLDB Python finalizers on exit.
    os._exit(code)


if __name__ == '__main__':
    main()
