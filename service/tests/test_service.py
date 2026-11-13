import io,json,os,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE/'runtime'))
from dayuan import native
from dayuan.broker import Broker,serve,request
ROOT=Path(__file__).resolve().parents[2]
_FIXTURE_TEMP=tempfile.TemporaryDirectory(prefix='dayuan-native-test-',dir='/private/tmp')
FIXTURE=Path(_FIXTURE_TEMP.name)/'native_fixture'
subprocess.run(['/usr/bin/clang','-g','-fobjc-arc','-framework','Foundation',str(Path(__file__).with_name('native_fixture.m')),'-o',str(FIXTURE)],check=True)


class FakeNative:
 def __init__(self):self.calls=[];self.ready=False;self.fail_submit=False;self.fail_poll=False
 def __call__(self,data):
  self.calls.append(data)
  if data['action'] in ('doctor','prepare'):return {'pid':123,'session':'s1','ready':True}
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

class BackgroundSessionTests(unittest.TestCase):
 def test_closed_assistant_is_prepared_before_single_dispatch(self):
  calls=[];attempts=[0]
  def native_call(payload):
   calls.append(payload['action'])
   if payload['action']=='prepare':
    attempts[0]+=1
    return {'ready':attempts[0]>1,'session':'headless' if attempts[0]>1 else None,'pid':123,'window_attached':False}
   self.assertEqual(payload['action'],'submit')
   self.assertEqual(payload['session'],'headless')
   return {'submitted':True,'session':'headless','pid':123}
  bridge=Broker(native_call)
  job=bridge.submit('read document')
  self.assertEqual(job['status'],'running')
  self.assertEqual(calls,['prepare','prepare','submit'])
 def test_failed_session_creation_never_dispatches_a_query(self):
  calls=[]
  def native_call(payload):
   calls.append(payload['action'])
   return {'ready':False,'session':None,'pid':123,'window_attached':False}
  bridge=Broker(native_call)
  from unittest.mock import patch
  with patch.object(bridge.stopping,'wait',return_value=False):
   with self.assertRaisesRegex(RuntimeError,'BACKGROUND_SESSION_NOT_READY'):bridge.submit('read document')
  self.assertTrue(calls)
  self.assertTrue(all(action=='prepare' for action in calls))
  self.assertIsNone(bridge.active_job)
 def test_visible_controller_is_rejected_before_dispatch(self):
  calls=[]
  def native_call(payload):
   calls.append(payload['action'])
   return {'ready':True,'session':'s1','pid':123,'window_attached':True}
  bridge=Broker(native_call)
  with self.assertRaisesRegex(RuntimeError,'BACKGROUND_CONTROLLER_HAS_WINDOW'):bridge.submit('read document')
  self.assertEqual(calls,['prepare'])
  self.assertIsNone(bridge.active_job)

class WorkerSubmissionTests(unittest.TestCase):
 def test_async_append_does_not_bind_the_previous_outgoing_message(self):
  from dayuan.worker import NativeSession
  session=object.__new__(NativeSession);session.pid=123
  session.doctor=lambda:{'ready':True}
  session.session_id=lambda:'same-session'
  values=iter(['baseline','previous-outgoing','previous-outgoing'])
  session.string=lambda expression:next(values)
  session.number=lambda expression:1
  out=session.handle({'action':'submit','session':'same-session','message_baseline_key':'baseline','prompt':'task'})
  self.assertTrue(out['submitted']);self.assertIsNone(out['sent_message_key'])

class NativeTests(unittest.TestCase):
 def call(self,payload):
  env=dict(os.environ,PYTHONPATH=str(SERVICE/'runtime'))
  p=subprocess.run(['/usr/bin/python3','-m','dayuan.worker','--fixture',str(FIXTURE)],input=json.dumps(payload),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env=env,cwd="/private/tmp")
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
 def test_missing_begin_marker_uses_native_completion(self):
  out=self.call({'action':'result','begin':'BEGIN_single','end':'END_single'})
  self.assertTrue(out['ready']);self.assertEqual(out['text'],'只有尾标记的答复')
 def test_empty_outgoing_text_is_correlated_by_message_key(self):
  out=self.call({'action':'result','begin':'BEGIN_native','end':'END_native','sent_message_key':'sent-native'})
  self.assertTrue(out['ready']);self.assertEqual(out['text'],'完整答复\n| 字段 | 内容 |')
  self.assertEqual(out['result_source'],'native_completion')
 def test_baseline_correlates_without_visible_outgoing_text(self):
  out=self.call({'action':'result','begin':'BEGIN_native','end':'END_native','message_baseline_key':'baseline-native'})
  self.assertTrue(out['ready']);self.assertEqual(out['sent_message_key'],'sent-native')
 def test_streaming_reply_is_not_complete(self):
  out=self.call({'action':'result','begin':'BEGIN_stream','end':'END_stream','sent_message_key':'sent-stream'})
  self.assertFalse(out['ready'])
 def test_finished_progress_does_not_hide_streaming_final(self):
  out=self.call({'action':'result','begin':'BEGIN_multi','end':'END_multi','sent_message_key':'sent-multi'})
  self.assertFalse(out['ready'])
 def test_markers_inside_unfinished_reply_are_not_completion(self):
  out=self.call({'action':'result','begin':'BEGIN_pending','end':'END_pending'})
  self.assertFalse(out['ready'])
 def test_unknown_anchor_never_returns_another_tasks_answer(self):
  out=self.call({'action':'result','begin':'BEGIN_unknown','end':'END_unknown','sent_message_key':'sent-unknown'})
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
   if payload['action'] in ('doctor','prepare'):return {'ready':True,'session':'s1','pid':456}
   if payload['action']=='result' and payload['pid']==123:raise RuntimeError('CLIENT_PID_INVALID')
   if payload['action']=='result' and payload['pid']==456:return {'ready':True,'text':'recovered'}
   self.fail('Unexpected resubmission')
  bridge.native_call=restarted
  self.assertEqual(bridge.result(job['job_id'])['text'],'recovered')
  self.assertFalse(any(x['action']=='submit' for x in calls))
 def test_client_restart_never_follows_a_different_session(self):
  bridge=Broker(FakeNative());job=bridge.submit('query')
  def wrong_session(payload):
   if payload['action'] in ('doctor','prepare'):return {'ready':True,'session':'another','pid':456}
   self.assertEqual(payload['pid'],123);raise RuntimeError('CLIENT_PID_INVALID')
  bridge.native_call=wrong_session
  result=bridge.result(job['job_id']);self.assertEqual(result['poll_error'],'SESSION_CHANGED')
  self.assertEqual(bridge.jobs[job['job_id']]['pid'],123)

if __name__=='__main__':unittest.main(verbosity=2)
