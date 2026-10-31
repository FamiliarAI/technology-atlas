"""All writes use disposable databases; the user's database is never a test fixture."""
import unittest,sys,json,sqlite3,tempfile,threading,urllib.request,urllib.error,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from database import Database,APIError,ROOT,encode
from serve import make_server

def item(id='test-only',**overrides):return dict(id=id,title='Synthetic test only',url='https://example.org/test-only',summary='Synthetic test, not a scientific event.',limits='No verification or scientific claim.',milestoneId='ROB-01',createdAt='2026-10-30T18:00:00Z',**overrides)
class DBTest(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.db=Database(self.path)
 def tearDown(self):self.temp.cleanup()
 def test_exact_seed_content_counts_provenance_and_duplicate_integrity(self):
  bootstrap=self.db.bootstrap();counts=self.db.counts()
  self.assertEqual([counts[k] for k in ['milestones','fields','tree_relationships','collection_relationships','branches','evidence','associations']],[660,66,len(bootstrap['tree']['edges']),2,len(bootstrap['tree']['branches']),9,10])
  for key,name in [('collection','milestones'),('tree','tree'),('evidence','evidence')]:
   original=json.loads((ROOT/'web/data'/f'{name}.json').read_text());actual=bootstrap[key]
   if key=='collection':actual=dict(actual,history=[h for h in actual['history'] if h['id']!='first-directed-tree'])
   self.assertEqual(actual,original)
  self.assertEqual(sum(bool(m['duplicateOf']) for m in bootstrap['collection']['milestones']),13)
  with self.db.connection() as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[]);self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_restart_is_idempotent_and_does_not_reseed_later_changes(self):
  self.db.create_submission(item())
  with self.db.connection(write=True) as c:
   data=json.loads(c.execute("SELECT payload FROM milestones WHERE id='ROB-01'").fetchone()[0]);data['title']='Test database edit';c.execute("UPDATE milestones SET payload=? WHERE id='ROB-01'",(encode(data),))
  counts=self.db.counts();restarted=Database(self.path,seed_dir=Path(self.temp.name)/'absent-seeds')
  self.assertEqual(restarted.counts(),counts);self.assertEqual(restarted.desk()['submissions'][0]['id'],'test-only')
  self.assertEqual(next(m for m in restarted.bootstrap()['collection']['milestones'] if m['id']=='ROB-01')['title'],'Test database edit')
 def test_transaction_foreign_key_failure_rolls_back_all_writes(self):
  with self.assertRaises(sqlite3.IntegrityError):
   with self.db.connection(write=True) as c:
    c.execute("INSERT INTO settings VALUES ('test-rollback','temporary')");c.execute("UPDATE milestones SET field='MISSING' WHERE id='ROB-01'")
  with self.db.connection() as c:self.assertIsNone(c.execute("SELECT * FROM settings WHERE key='test-rollback'").fetchone())
 def test_new_submission_cannot_promote_itself_and_invalid_target_is_rejected(self):
  for extra in [{'state':'verified'},{'scientificallyVerified':True},{'version':50}]:
   with self.assertRaises(APIError):self.db.create_submission(item()|extra)
  with self.assertRaises(APIError):self.db.create_submission(item()|{'milestoneId':'MISSING'})
  with self.assertRaises(APIError):self.db.create_submission(item()|{'createdAt':123})
  self.assertEqual(self.db.counts()['submissions'],0)
 def test_create_retry_is_idempotent_but_content_conflict_is_not_overwritten(self):
  first=self.db.create_submission(item());second=self.db.create_submission(item());self.assertEqual(first,second)
  with self.assertRaises(APIError) as error:self.db.create_submission(item()|{'summary':'Different test content'})
  self.assertEqual(error.exception.status,409);self.assertEqual(self.db.counts()['review_activity'],1)
 def test_optimistic_review_version_prevents_lost_updates(self):
  first=self.db.create_submission(item());updated=self.db.dismiss(first['id'],{'state':'dismissed','version':1});self.assertEqual(updated['version'],2)
  with self.assertRaises(APIError) as error:self.db.dismiss(first['id'],{'state':'dismissed','version':1})
  self.assertEqual(error.exception.status,409);self.assertEqual(self.db.counts()['review_activity'],2)
  with self.assertRaises(APIError):self.db.dismiss(first['id'],{'state':'verified','version':2})
 def test_browser_migration_preserves_exact_raw_and_is_idempotent_across_restarts(self):
  raw=json.dumps({'schemaVersion':2,'submissions':[item()|{'state':'dismissed'}]},indent=3)
  snapshots={'snapshots':[{'key':'techtree-evidence-desk-v2','raw':raw}]}
  first=self.db.migrate_browser(snapshots);self.assertEqual(first['reports'][0]['added'],1);counts=self.db.counts()
  second=Database(self.path).migrate_browser(snapshots);self.assertTrue(second['reports'][0]['alreadyImported']);self.assertEqual(counts,self.db.counts())
  self.assertEqual(self.db.export()['browserSnapshots'][0]['raw'],raw);self.assertEqual(self.db.desk()['submissions'][0]['state'],'dismissed')
 def test_migration_conflicts_preserve_both_copies_and_bad_raw(self):
  self.db.create_submission(item());before=self.db.desk()
  conflicting=item()|{'summary':'Different saved browser content','state':'pending-source-review'}
  report=self.db.migrate_browser({'snapshots':[{'key':'techtree-evidence-desk-v2','raw':json.dumps({'schemaVersion':2,'submissions':[conflicting]})},{'key':'techtree-state-v1','raw':'not-json-raw-sentinel'}]})
  self.assertEqual(report['conflicts'],1);self.assertEqual(self.db.desk(),before);self.assertTrue(report['reports'][1]['issues'])
  exported=self.db.export();self.assertEqual(len(exported['browserSnapshots']),2);self.assertIn('Different saved browser content',exported['migrationConflicts'][0]['payload'])
 def test_legacy_revisions_and_reviews_are_archived_without_applying_claims(self):
  legacy={'schemaVersion':1,'baseVersion':'old','proposals':[{'id':'p1','event':{'id':'old'},'change':{'status':'observed'},'state':'accepted'}],'revisions':[{'number':1,'event':{'title':'Unverified synthetic test'},'change':{'status':'observed'}}]}
  snapshots={'snapshots':[{'key':'techtree-state-v1','raw':json.dumps(legacy)}]};before=self.db.bootstrap()
  self.db.migrate_browser(snapshots);counts=self.db.counts();self.assertEqual(counts['legacy_records'],2);self.assertEqual(counts['submissions'],0)
  self.assertEqual(before['evidence'],self.db.bootstrap()['evidence']);self.assertEqual(before['tree'],self.db.bootstrap()['tree'])
  self.assertEqual(self.db.activity()['revisions'][-1]['scope'],'legacy-unverified');self.db.migrate_browser(snapshots);self.assertEqual(self.db.counts(),counts)
 def test_consistent_backup_restores_rows_reviews_and_schema(self):
  self.db.create_submission(item());self.db.dismiss('test-only',{'state':'dismissed','version':1});destination=Path(self.temp.name)/'backup.sqlite3';self.db.backup(destination)
  restored=Database(destination);self.assertEqual(self.db.bootstrap(),restored.bootstrap())
 def test_two_concurrent_writers_both_survive(self):
  errors=[]
  def write(id):
   try:self.db.create_submission(item(id))
   except Exception as e:errors.append(e)
  threads=[threading.Thread(target=write,args=(f'test-{i}',)) for i in range(2)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(errors,[]);self.assertEqual(self.db.counts()['submissions'],2)

class APITest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.server=make_server(Path(self.temp.name)/'api.sqlite3',0);self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start();self.url=f'http://localhost:{self.server.server_port}'
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
 def request(self,path,method='GET',body=None,headers=None):
  req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json',**(headers or {})})
  try:r=urllib.request.urlopen(req,timeout=5)
  except urllib.error.HTTPError as error:r=error
  with r:return r.status,r.headers,r.read()
 def test_api_core_is_database_backed_and_seed_routes_are_not_runtime_fallback(self):
  status,_,raw=self.request('/api/bootstrap');self.assertEqual(status,200);self.assertEqual(len(json.loads(raw)['collection']['milestones']),660)
  self.assertEqual(self.request('/data/tree.json')[0],410);self.assertEqual(self.request('/api/no-such-route')[0],404)
 def test_api_validation_csrf_and_stale_update_errors(self):
  self.assertEqual(self.request('/api/submissions','POST',item()|{'state':'verified'})[0],400)
  self.assertEqual(self.request('/api/submissions','POST',item(),{'Origin':'https://untrusted.example'})[0],403)
  status,_,raw=self.request('/api/submissions','POST',item());self.assertEqual(status,201);self.assertEqual(json.loads(raw)['state'],'pending-source-review')
  self.assertEqual(self.request('/api/submissions/test-only','PATCH',{'state':'dismissed','version':1})[0],200)
  self.assertEqual(self.request('/api/submissions/test-only','PATCH',{'state':'dismissed','version':1})[0],409)
 def test_api_backup_is_a_real_restorable_sqlite_database(self):
  status,headers,raw=self.request('/api/backup');self.assertEqual(status,200);self.assertTrue(raw.startswith(b'SQLite format 3\x00'));self.assertIn('attachment',headers['Content-Disposition'])
  path=Path(self.temp.name)/'download.sqlite3';path.write_bytes(raw);self.assertEqual(Database(path).counts()['milestones'],660)
 def test_actual_backend_process_restart_preserves_saved_state(self):
  path=Path(self.temp.name)/'restart.sqlite3'
  def start():
   process=subprocess.Popen([sys.executable,str(ROOT/'scripts/serve.py'),'--db',str(path),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
   line=process.stdout.readline().strip();return process,line.split(' at ')[1]
  process,url=start()
  try:
   req=urllib.request.Request(url+'/api/submissions',data=json.dumps(item('process-test')).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=5) as r:self.assertEqual(r.status,201)
  finally:process.terminate();process.wait(timeout=5);process.stdout.close()
  process,url=start()
  try:
   with urllib.request.urlopen(url+'/api/desk',timeout=5) as r:saved=json.load(r)
   self.assertEqual(saved['submissions'][0]['id'],'process-test')
  finally:process.terminate();process.wait(timeout=5);process.stdout.close()

if __name__=='__main__':unittest.main()
