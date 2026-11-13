"""Fixed-operation worker; cache symbols, never retain an attached client."""
import json,os,select,subprocess,threading,time
from pathlib import Path

class NativeTransport:
    def __init__(self):
        self.process=None;self.buffer=b'';self.lock=threading.Lock();self.completed=0

    def close(self):
        proc=self.process;self.process=None;self.buffer=b'';self.completed=0
        if proc is None:return
        try:
            if proc.stdin:proc.stdin.close()
            proc.wait(timeout=2)
        except (OSError,subprocess.TimeoutExpired):
            proc.kill();proc.wait(timeout=5)
        finally:
            if proc.stdout:proc.stdout.close()

    def request(self,payload,timeout=45):
        with self.lock:
            if self.process is None or self.process.poll() is not None or self.completed >= 128:
                self.close()
                env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','PYTHONPATH':str(Path(__file__).resolve().parents[1]),'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'}
                self.process=subprocess.Popen(['/usr/bin/python3','-m','dayuan.worker','--persistent'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,bufsize=0)
            proc=self.process;deadline=time.monotonic()+timeout
            try:
                data=json.dumps(payload,ensure_ascii=True).encode()+b'\n'
                # Use a bounded nonblocking write as macOS pipe buffers can be
                # smaller than the maximum task. Never restart/replay a request.
                fd=proc.stdin.fileno();os.set_blocking(fd,False)
                while data:
                    left=deadline-time.monotonic()
                    if left<=0 or not select.select([], [fd], [], left)[1]:raise TimeoutError('NATIVE_WORKER_TIMEOUT')
                    try:n=os.write(fd,data);data=data[n:]
                    except BlockingIOError:continue
                fd=proc.stdout.fileno()
                while b'\n' not in self.buffer:
                    left=deadline-time.monotonic()
                    if left<=0 or not select.select([fd], [], [], left)[0]:raise TimeoutError('NATIVE_WORKER_TIMEOUT')
                    chunk=os.read(fd,65536)
                    if not chunk:raise RuntimeError('NATIVE_WORKER_EXITED')
                    self.buffer+=chunk
                    if len(self.buffer)>1048576:raise RuntimeError('NATIVE_RESPONSE_TOO_LARGE')
                line,self.buffer=self.buffer.split(b'\n',1)
                value=json.loads(line)
                if not isinstance(value,dict):raise RuntimeError('INVALID_NATIVE_RESPONSE')
                self.completed+=1
                return value
            except Exception:
                self.close();raise
