"""Per-innovation evidence safety and durable import checks on disposable databases."""
import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from database import Database,ROOT,APIError
from source_audit import initialize,ingest,snapshot,claim_hash
from database_test import item
class SourceAuditTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'test.sqlite3');initialize(self.db)
  self.assign=json.loads((ROOT/'research/source-audit/assignments/field-01.json').read_text())
  self.batch={'batchId':'field-01','field':self.assign['field'],'checkedAt':'2026-10-31T00:00:00Z','verifier':{'model':'synthetic-test'},'sourceChecks':[],'innovations':[{'milestoneId':m['id'],'claimHash':m['claimHash'],'overall':'unsupported','summary':'Synthetic test: no source supports this claim.','claims':[{'claim':m['description'],'classification':'unsupported','sourceIds':[],'scope':'Synthetic test only','limitations':'No scientific validation'}],'evidence':[],'searchLog':[{'query':'synthetic test','outcome':'No external research performed in this test'}]} for m in self.assign['innovations']]}
 def tearDown(self):self.temp.cleanup()
 def test_queue_exactly_preserves_all_660_claims_across_restart(self):
  before=self.db.bootstrap();self.assertEqual(snapshot(self.db)['summary']['pending'],660)
  with self.db.connection() as c:
   rows=c.execute('SELECT * FROM source_audit_queue').fetchall();self.assertEqual(len(rows),660)
   for r in rows:
    m=next(m for m in before['collection']['milestones'] if m['id']==r['milestone_id']);self.assertEqual(r['claim_hash'],claim_hash(m));self.assertEqual(json.loads(r['payload'])['description'],m['description'])
  initialize(Database(self.db.path));self.assertEqual(self.db.bootstrap(),before)
 def test_agent_results_never_count_as_checked_before_controller_review(self):
  ingest(self.db,self.batch);s=snapshot(self.db);self.assertEqual(s['summary']['checked'],0);self.assertEqual(s['summary']['agentReviewed'],10)
  review={'accepted':True,'reviewer':'Synthetic test controller','notes':'Test only; no real scientific claim.'};ingest(self.db,self.batch,review)
  self.assertEqual(snapshot(self.db)['summary']['checked'],10);self.assertEqual(snapshot(self.db)['summary']['statuses'],{'unsupported':10})
 def test_retry_preserves_submissions_tree_sources_and_rejects_changed_batch(self):
  self.db.create_submission(item());before=self.db.bootstrap();ingest(self.db,self.batch);self.assertTrue(ingest(self.db,self.batch)['alreadyImported']);after=self.db.bootstrap()
  for k in ['collection','tree','desk','evidence']:self.assertEqual(before[k],after[k])
  changed=json.loads(json.dumps(self.batch));changed['innovations'][0]['summary']='Changed'
  with self.assertRaises(APIError):ingest(self.db,changed)
  self.assertEqual(snapshot(self.db)['summary']['agentReviewed'],10)
 def test_failed_or_snippet_sources_cannot_substantiate_positive_claim(self):
  self.batch['innovations'][0]['overall']='partial-progress'
  with self.assertRaisesRegex(APIError,'lacks read'):ingest(self.db,self.batch)
  self.assertEqual(snapshot(self.db)['summary']['agentReviewed'],0)
 def test_stale_claim_hash_and_missing_item_reject_atomically(self):
  self.batch['innovations'][0]['claimHash']='stale'
  with self.assertRaises(APIError):ingest(self.db,self.batch)
  self.assertEqual(snapshot(self.db)['summary']['pending'],660)
  self.batch['innovations'].pop()
  with self.assertRaises(APIError):ingest(self.db,self.batch)
 def test_explicit_correction_keeps_prior_batch_and_rejects_wrong_base(self):
  from source_audit import fingerprint
  ingest(self.db,self.batch,{'accepted':True,'reviewer':'Synthetic controller','notes':'Test only'})
  corrected=json.loads(json.dumps(self.batch));corrected['revision']=2;corrected['supersedesHash']='wrong'
  with self.assertRaises(APIError):ingest(self.db,corrected)
  corrected['supersedesHash']=fingerprint(self.batch);corrected['innovations'][0]['summary']='Explicit test correction'
  review={'accepted':True,'reviewer':'Synthetic controller','notes':'Correction test'};ingest(self.db,corrected,review)
  with self.db.connection() as c:before=c.execute('SELECT COUNT(*) FROM source_audit_history').fetchone()[0];self.assertEqual(c.execute('SELECT COUNT(*) FROM source_audit_batches').fetchone()[0],2)
  ingest(self.db,corrected,review)
  with self.db.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM source_audit_history').fetchone()[0],before)
  self.assertEqual(snapshot(self.db)['innovations'][0]['summary'],'Explicit test correction')
  self.assertEqual(snapshot(self.db)['summary']['revision'],2)
