"""Content upgrade checks use temporary databases only."""
import unittest,tempfile,json,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from database import Database,ROOT,APIError
from apply_connection_migration import apply,validate_graph
from database_test import item
PATCH=json.loads((ROOT/'research/connection-review/current-patch.json').read_text())
class ConnectionMigrationTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);seed=self.root/'seed';shutil.copytree(ROOT/'web/data',seed)
  shutil.copy(ROOT/'research/connection-review/baseline-tree.json',seed/'tree.json');self.path=self.root/'test.sqlite3';self.db=Database(self.path,seed_dir=seed);self.db.create_submission(item());self.desk=self.db.desk();self.original=self.db.bootstrap()['collection']
 def tearDown(self):self.temp.cleanup()
 def test_upgrade_restart_and_retry_preserve_sources_submissions_and_full_review(self):
  result=apply(self.db,PATCH);self.assertEqual(result['edgesAdded'],341);self.assertEqual(self.db.bootstrap()['collection'],self.original);self.assertEqual(self.db.desk(),self.desk)
  current=self.db.bootstrap()['tree'];seed=json.loads((ROOT/'web/data/tree.json').read_text());self.assertEqual(current,seed)
  reopened=Database(self.path);self.assertTrue(apply(reopened,PATCH)['alreadyApplied']);self.assertEqual(reopened.bootstrap()['tree'],current);self.assertEqual(reopened.desk(),self.desk)
  with reopened.connection() as c:validate_graph(c)
 def test_cycle_rolls_back_edges_reviews_and_submission_history_unchanged(self):
  patch=json.loads(json.dumps(PATCH));edge=json.loads(json.dumps(self.db.bootstrap()['tree']['edges'][0]));edge['id']='EXP-test-cycle';edge['fromId'],edge['toId']=edge['toId'],edge['fromId'];edge['kind']='required';edge['requiredScope']='Synthetic test';patch['edges'].append(edge);before=self.db.bootstrap();counts=self.db.counts()
  with self.assertRaisesRegex(APIError,'cycle'):apply(self.db,patch)
  self.assertEqual(self.db.bootstrap(),before);self.assertEqual(self.db.counts(),counts);self.assertEqual(self.db.desk(),self.desk)
 def test_source_guard_and_version_conflict_refuse_changes(self):
  patch=json.loads(json.dumps(PATCH));patch['sourceHashes']['ROB-01']='changed';before=self.db.counts()
  with self.assertRaises(APIError):apply(self.db,patch)
  self.assertEqual(self.db.counts(),before);apply(self.db,PATCH);patch=json.loads(json.dumps(PATCH));patch['title']='different'
  with self.assertRaises(APIError):apply(self.db,patch)
 def test_explicit_retirement_checks_payload_before_deleting_and_keeps_audit(self):
  previous=json.loads((ROOT/'research/connection-review/current-patch.json').read_text());previous['version']='synthetic-pre-prune';previous['edges'] += [r['expectedPayload'] for r in previous['retiredEdges']];previous['retiredEdges']=[]
  # Pre-prune proposals were still a valid acyclic conceptual graph.
  apply(self.db,previous);result=apply(self.db,PATCH);self.assertEqual(result['edgesRemoved'],12);self.assertEqual(self.db.counts()['tree_relationships'],444);self.assertEqual(self.db.desk(),self.desk)
