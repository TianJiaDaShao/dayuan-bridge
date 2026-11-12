import io,json,os,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE/'runtime'))
from dayuan import native,mcp
from dayuan.broker import Broker,serve,request
ROOT=Path(__file__).resolve().parents[2]
FIXTURE=Path(__file__).with_name('native_fixture')
if not FIXTURE.exists():subprocess.run(['/usr/bin/clang','-g','-fobjc-arc','-framework','Foundation',str(FIXTURE.with_suffix('.m')),'-o',str(FIXTURE)],check=True)

class FakeNative:
 def __init__(self):self.calls=[];self.ready=False;self.fail_submit=False;self.fail_poll=False
 def __call__(self,data):
  self.calls.append(data)
  if data['action']=='doctor':return {'pid':123,'session':'s1','ready':True}
  if data['action']=='submit':
   if self.fail_submit:raise RuntimeError('worker stopped after dispatch')
   return {'pid':123,'session':'s1','submitted':True}
  if self.fail_poll:raise RuntimeError('SESSION_CHANGED')
  return {'ready':self.ready,'text':'table result' if self.ready else None}

class BrokerTests(unittest.TestCase):
 def setUp(self):self.fake=FakeNative();self.broker=Broker(self.fake)
 def test_submission_serialization_and_recovery(self):
  job=self.broker.submit('query');self.assertEqual(job['status'],'running')
  with self.assertRaises(RuntimeError):self.broker.submit('duplicate')
  self.assertEqual(self.broker.result(job['job_id'])['status'],'running')
  self.fake.ready=True
  final=self.broker.result(job['job_id']);self.assertEqual(final['text'],'table result')
  count=len(self.fake.calls);self.assertEqual(self.broker.result(job['job_id']),final)
  self.assertEqual(len(self.fake.calls),count)
  self.assertEqual(sum(x['action']=='submit' for x in self.fake.calls),1)
 def test_uncertain_dispatch_is_not_retried(self):
  self.fake.fail_submit=True;job=self.broker.submit('query')
  self.assertEqual(job['status'],'unknown');self.assertIn('SUBMISSION_UNCONFIRMED',job['error'])
  with self.assertRaises(RuntimeError):self.broker.submit('duplicate')
  self.fake.ready=True;final=self.broker.result(job['job_id']);self.assertEqual(final['status'],'complete');self.assertNotIn('error',final)
 def test_session_change_preserves_job(self):
  job=self.broker.submit('query');self.fake.fail_poll=True
  final=self.broker.result(job['job_id']);self.assertEqual(final['status'],'running');self.assertEqual(final['poll_error'],'SESSION_CHANGED')
 def test_invalid_task(self):
  for task in ['',None,42,'x'*20001,'nul\x00','\ud800']:
   with self.assertRaises(ValueError):self.broker.submit(task)
  self.assertFalse(self.fake.calls)
 def test_no_generic_native_or_shell_operation(self):
  for method in ['exec','eval','native','open','__import__']:
   with self.assertRaises(ValueError):self.broker.handle({'method':method,'code':'id'})
 def test_private_unix_transport(self):
  with tempfile.TemporaryDirectory(prefix='dy-') as temp:
   path=Path(temp)/'b.sock';ready=threading.Event()
   thread=threading.Thread(target=serve,args=(os.getuid(),os.getgid()),kwargs={'path':path,'broker':self.broker,'ready':ready.set},daemon=True)
   thread.start();self.assertTrue(ready.wait(3))
   self.assertEqual(path.stat().st_mode & 0o777,0o600)
   self.assertTrue(request({'method':'status'},path=path)['ready'])
   with self.assertRaises(RuntimeError):request({'method':'exec'},path=path)
   request({'method':'shutdown'},path=path);thread.join(3);self.assertFalse(thread.is_alive());self.assertFalse(path.exists())

class MCPTests(unittest.TestCase):
 def test_initialize_and_notification(self):
  self.assertIsNone(mcp.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'}))
  out=mcp.dispatch({'id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}})
  self.assertEqual(out['result']['protocolVersion'],'2025-03-26')
  self.assertEqual(len(mcp.dispatch({'id':2,'method':'tools/list'})['result']['tools']),3)
 def test_tool_error_is_explicit(self):
  out=mcp.dispatch({'id':1,'method':'tools/call','params':{'name':'exec'}})
  self.assertTrue(out['result']['isError'])
 def test_stdio_protocol_clean(self):
  source=io.StringIO('{"id":1,"method":"ping"}\n{"method":"notifications/initialized"}\nBAD\n')
  sink=io.StringIO();mcp.serve_stdio(source,sink)
  rows=[json.loads(x) for x in sink.getvalue().splitlines()];self.assertEqual(len(rows),2);self.assertEqual(rows[1]['error']['code'],-32700)

class NativeTests(unittest.TestCase):
 def call(self,payload):
  env=dict(os.environ,PYTHONPATH=str(SERVICE/'runtime'))
  p=subprocess.run(['/usr/bin/python3','-m','dayuan.worker','--fixture',str(FIXTURE)],input=json.dumps(payload),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,env=env)
  self.assertEqual(p.returncode,0,p.stderr+'\n'+p.stdout)
  data=json.loads(p.stdout);self.assertTrue(data['ok'],data);self.assertTrue(data['cleanup']['detached']);return data['data']
 def test_dynamic_lookup_and_repeated_clean_detach(self):
  for _ in range(6):
   out=self.call({'action':'doctor'});self.assertTrue(out['ready']);self.assertEqual(out['session'],'fixture-session')
 def test_long_result_retains_table_and_ignores_preamble(self):
  out=self.call({'action':'result','session':'fixture-session','begin':'BEGIN_fixture','end':'END_fixture'})
  self.assertTrue(out['ready']);self.assertEqual(out['text'],'| Field | Value |\n| a | b |')
 def test_outgoing_messages_are_not_answers(self):
  out=self.call({'action':'result','begin':'BEGIN_outgoing','end':'END_outgoing'})
  self.assertFalse(out['ready'])
 def test_prompt_escaping_real_objc_dispatch(self):
  out=self.call({'action':'submit','prompt':'Chinese: \u4e2d\u6587 \U0001f680\n"quote" \\ $(touch /tmp/not-run)'});self.assertTrue(out['submitted'])

class ServiceTests(unittest.TestCase):
 def test_peer_identity_from_kernel(self):
  import socket
  from dayuan.service import peer_uid
  a,b=socket.socketpair()
  try:self.assertEqual(peer_uid(a),os.getuid())
  finally:a.close();b.close()
 def test_persistent_uncertain_job_recovers_without_resubmission(self):
  with tempfile.TemporaryDirectory() as temp:
   state=Path(temp)/'jobs.json';fake=FakeNative();fake.fail_submit=True
   first=Broker(fake,state_path=state);job=first.submit('persist this task')
   self.assertEqual(state.stat().st_mode & 0o777,0o600)
   second=Broker(fake,state_path=state);self.assertEqual(second.active_job,job['job_id'])
   self.assertEqual(second.jobs[job['job_id']]['status'],'unknown')
   fake.ready=True;self.assertEqual(second.result(job['job_id'])['status'],'complete')
   self.assertEqual(sum(x['action']=='submit' for x in fake.calls),1)
   third=Broker(fake,state_path=state);self.assertIsNone(third.active_job)
   self.assertEqual(third.result(job['job_id'])['text'],'table result')
 def test_job_state_symlink_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   target=Path(temp)/'real.json';target.write_text('{"schema":1,"jobs":[]}');target.chmod(0o600)
   link=Path(temp)/'jobs.json';link.symlink_to(target)
   with self.assertRaises(RuntimeError):Broker(FakeNative(),state_path=link)
 def test_owner_uid_prevents_cross_user_attach(self):
  from unittest.mock import patch
  from dayuan.worker import find_pid,EXE,BridgeError
  rows='501 10 '+EXE+'\n502 5 '+EXE+'\n501 15 '+EXE+' --renderer\n'
  with patch('dayuan.worker.subprocess.check_output',return_value=rows):
   self.assertEqual(find_pid(owner_uid=501),10)
   with self.assertRaises(BridgeError):find_pid(5,501)
   with self.assertRaises(BridgeError):find_pid(owner_uid=0)
 def test_unprivileged_service_config_is_rejected(self):
  from unittest.mock import patch
  from dayuan.service import configuration
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'service.json';path.write_text('{"owner_uid":501}');path.chmod(0o644)
   with patch('dayuan.service.CONFIG',path):
    with self.assertRaises(RuntimeError):configuration()
 def test_forget_preserves_record_and_frees_queue(self):
  fake=FakeNative();bridge=Broker(fake);job=bridge.submit('query')
  result=bridge.handle({'method':'forget','job_id':job['job_id']})
  self.assertTrue(result['remote_task_may_continue']);self.assertIsNone(bridge.active_job)
  self.assertIn(job['job_id'],bridge.jobs)

class RecoveryTests(unittest.TestCase):
 def test_client_restart_retargets_only_same_session(self):
  fake=FakeNative();bridge=Broker(fake);job=bridge.submit('query');calls=[]
  def restarted(payload):
   calls.append(payload)
   if payload['action']=='doctor':return {'ready':True,'session':'s1','pid':456}
   if payload['action']=='result' and payload['pid']==123:raise RuntimeError('CLIENT_PID_INVALID')
   if payload['action']=='result' and payload['pid']==456:return {'ready':True,'text':'recovered'}
   self.fail('Unexpected resubmission')
  bridge.native_call=restarted
  self.assertEqual(bridge.result(job['job_id'])['text'],'recovered')
  self.assertFalse(any(x['action']=='submit' for x in calls))
 def test_client_restart_never_follows_a_different_session(self):
  bridge=Broker(FakeNative());job=bridge.submit('query')
  def wrong_session(payload):
   if payload['action']=='doctor':return {'ready':True,'session':'another','pid':456}
   self.assertEqual(payload['pid'],123);raise RuntimeError('CLIENT_PID_INVALID')
  bridge.native_call=wrong_session
  result=bridge.result(job['job_id']);self.assertEqual(result['poll_error'],'SESSION_CHANGED')
  self.assertEqual(bridge.jobs[job['job_id']]['pid'],123)

if __name__=='__main__':unittest.main(verbosity=2)
