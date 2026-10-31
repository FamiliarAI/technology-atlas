"""Source role separation and migration safety on disposable databases."""
import unittest,tempfile,json,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from database import Database,ROOT
from source_audit import initialize,ingest,snapshot,fingerprint
from source_roles import backfill

class SourceRolesTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'roles.sqlite3');initialize(self.db)
  a=json.loads((ROOT/'research/source-audit/assignments/field-01.json').read_text());self.batch={'batchId':a['batchId'],'field':a['field'],'verifier':{'model':'synthetic-test'},'sourceChecks':[],'innovations':[]}
  for m in a['innovations']:self.batch['innovations'].append({'milestoneId':m['id'],'claimHash':m['claimHash'],'overall':'unsupported','summary':'Synthetic test only','claims':[{'claim':m['description'],'classification':'unsupported','sourceIds':[],'scope':'Not tested','limitations':'Synthetic fixture'}],'evidence':[],'searchLog':[{'query':'Synthetic fixture','outcome':'No actual research'}]})
  self.url=a['innovations'][0]['originalSourceLinks'][0];self.batch['sourceChecks']=[{'id':'s1','originalUrl':self.url,'origin':'original-notes','outcome':'retrieved','title':'Synthetic source','accessedAt':'2026-10-31','locator':'Test section','paraphrase':'Synthetic finding','limitations':'No real scientific claim','retrievalReference':'Synthetic receipt'}]
  i=self.batch['innovations'][0];i.update(overall='partial-progress',claims=[{'claim':'Synthetic compound claim','classification':'partial-progress','sourceIds':['s1'],'scope':'A small synthetic result','limitations':'Test only'}],evidence=[{'sourceId':'s1','classification':k,'supportedClaim':k+' synthetic finding','locator':'Test section','paraphrase':'Synthetic passage','limitations':'Test only'} for k in ['partial-progress','goal-supported','background-only']])
  self.review={'accepted':True,'reviewer':'Synthetic controller','notes':'Test fixture, no real scientific claim'}
 def tearDown(self):self.temp.cleanup()
 def test_backfill_separates_roles_from_origin_without_inventing_proposal_attribution(self):
  ingest(self.db,self.batch,self.review);before=self.db.export();backfill(self.db);s=snapshot(self.db);i=next(i for i in s['innovations'] if i['milestoneId']=='ACT-01');r=i['sourceRoles']
  self.assertEqual(r['proposalAttribution']['status'],'unconfirmed');self.assertEqual(r['proposalSources'][0]['attribution'],'field-bibliography')
  self.assertEqual(len(r['progressEvidence']),1);self.assertEqual(len(r['contextEvidence']),2)
  self.assertEqual(r['progressEvidence'][0]['origin'],'original-notes');self.assertEqual(r['progressEvidence'][0]['role'],'progress-evidence');self.assertEqual(r['proposalSources'][0]['url'],self.url)
  self.assertEqual(s['summary']['sourceRoles']['unconfirmedProposalAttribution'],660);self.assertEqual(s['summary']['sourceRoles']['withProgressEvidence'],1)
  after=self.db.export()
  for k in ['collection','tree','desk','evidence','sourceAuditBatches']:self.assertEqual(before[k],after[k])
  self.assertEqual(before['sourceAuditHistory'],after['sourceAuditHistory'][:len(before['sourceAuditHistory'])])
  self.assertEqual(len(after['sourceRoleAssignments']),660)
  with self.db.connection() as c:n=c.execute('SELECT count(*) FROM source_audit_history').fetchone()[0]
  self.assertEqual(backfill(self.db)['changed'],0)
  with self.db.connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM source_audit_history').fetchone()[0],n)
 def test_unreviewed_sources_never_become_progress(self):
  ingest(self.db,self.batch);backfill(self.db);i=next(i for i in snapshot(self.db)['innovations'] if i['milestoneId']=='ACT-01');self.assertEqual(i['sourceRoles']['progressEvidence'],[])
 def test_audit_correction_refreshes_persisted_roles_and_retains_previous_assignment(self):
  ingest(self.db,self.batch,self.review);backfill(self.db);b=copy.deepcopy(self.batch);b.update(revision=2,supersedesHash=fingerprint(self.batch));b['innovations'][0]['evidence'][0]['classification']='goal-supported';b['innovations'][0]['overall']='goal-supported';ingest(self.db,b,self.review)
  i=next(i for i in snapshot(self.db)['innovations'] if i['milestoneId']=='ACT-01');self.assertEqual(i['sourceRoles']['progressEvidence'],[]);self.assertEqual(len(i['sourceRoles']['contextEvidence']),3)
  with self.db.connection() as c:self.assertTrue(c.execute("SELECT count(*) FROM source_audit_history WHERE action='source-role-refresh'").fetchone()[0]>=2)

 def test_partial_audit_label_on_review_does_not_become_demonstrated_progress(self):
  self.batch['sourceChecks'][0]['sourceType']='review';ingest(self.db,self.batch,self.review);backfill(self.db);i=next(i for i in snapshot(self.db)['innovations'] if i['milestoneId']=='ACT-01')
  self.assertEqual(i['overall'],'partial-progress');self.assertEqual(i['sourceRoles']['progressEvidence'],[]);self.assertEqual(len(i['sourceRoles']['contextEvidence']),3)
