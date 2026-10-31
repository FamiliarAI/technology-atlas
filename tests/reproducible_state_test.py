"""The committed reviewed snapshot reproduces the real corpus without touching runtime data."""
import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from restore_project_state import restore,SNAPSHOT,TABLES
from source_audit import snapshot
from source_roles import backfill

class ReproducibleStateTest(unittest.TestCase):
 def test_real_reviewed_state_restores_with_history_and_refuses_overwrite(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'restored.sqlite3';d=restore(path);saved=json.loads(SNAPSHOT.read_text());s=snapshot(d)
   self.assertEqual(s['summary']['checked'],660);self.assertEqual(s['summary']['sourceRoles']['mapped'],660)
   with d.connection() as c:
    for t in TABLES:self.assertEqual([list(r) for r in c.execute('SELECT * FROM '+t)],saved['tables'][t]['rows'],t)
   self.assertEqual(backfill(d)['changed'],0)
   with self.assertRaisesRegex(ValueError,'Destination exists'):restore(path)
   self.assertEqual(snapshot(d),s)
 def test_tampered_snapshot_is_rejected_before_creating_database(self):
  with tempfile.TemporaryDirectory() as directory:
   data=json.loads(SNAPSHOT.read_text());data['tables']['source_audit_assessments']['rows'].pop();bad=Path(directory)/'bad.json';bad.write_text(json.dumps(data));target=Path(directory)/'never.sqlite3'
   with self.assertRaisesRegex(ValueError,'hash mismatch'):restore(target,bad)
   self.assertFalse(target.exists())
