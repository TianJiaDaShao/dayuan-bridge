import json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from dayuan.native_transport import NativeTransport

class TransportTests(unittest.TestCase):
 def test_multiple_requests_share_one_worker_and_large_tasks_are_written(self):
  original=subprocess.Popen;created=[]
  program='import sys,json\nfor line in sys.stdin:\n d=json.loads(line);print(json.dumps({"ok":True,"length":len(d["task"])}),flush=True)\n'
  def launch(*args,**kwargs):
   proc=original([sys.executable,'-u','-c',program],**kwargs);created.append(proc);return proc
  transport=NativeTransport()
  try:
   with patch('dayuan.native_transport.subprocess.Popen',side_effect=launch):
    for task in ['short','中'*20000,'third']:
     self.assertEqual(transport.request({'task':task})['length'],len(task))
    self.assertEqual(len(created),1)
  finally:transport.close()
  self.assertIsNotNone(created[0].poll())
 def test_timeout_discards_worker_without_replaying_request(self):
  original=subprocess.Popen;created=[]
  program='import sys,time\nsys.stdin.readline()\ntime.sleep(10)\n'
  def launch(*args,**kwargs):
   proc=original([sys.executable,'-u','-c',program],**kwargs);created.append(proc);return proc
  transport=NativeTransport()
  try:
   with patch('dayuan.native_transport.subprocess.Popen',side_effect=launch):
    with self.assertRaisesRegex(TimeoutError,'NATIVE_WORKER_TIMEOUT'):transport.request({'action':'submit'},timeout=.1)
    self.assertEqual(len(created),1)
    self.assertIsNone(transport.process)
  finally:transport.close()
 def test_non_json_worker_output_is_rejected_and_worker_reaped(self):
  original=subprocess.Popen;created=[]
  def launch(*args,**kwargs):
   proc=original([sys.executable,'-u','-c','import sys;sys.stdin.readline();print("invalid",flush=True)'],**kwargs);created.append(proc);return proc
  transport=NativeTransport()
  try:
   with patch('dayuan.native_transport.subprocess.Popen',side_effect=launch):
    with self.assertRaises(ValueError):transport.request({'action':'doctor'})
   self.assertIsNone(transport.process)
   self.assertIsNotNone(created[0].poll())
  finally:transport.close()
if __name__=='__main__':unittest.main()
