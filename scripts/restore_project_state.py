"""Restore reviewed project records into a NEW local database; never overwrite runtime data."""
import argparse,json
from pathlib import Path
from database import Database,ROOT,encode,digest
from source_audit import SCHEMA as AUDIT_SCHEMA,claim_hash
from source_roles import SCHEMA as ROLE_SCHEMA

TABLES=('documents','fields','milestones','evidence','associations','relationships','relationship_evidence','branches','branch_nodes','connection_reviews','revisions','source_audit_queue','source_audit_batches','source_audit_checks','source_audit_assessments','source_audit_evidence','source_audit_history','source_role_assignments')
SNAPSHOT=ROOT/'research/reviewed-project-state.json'

def restore(destination,snapshot=SNAPSHOT):
 destination=Path(destination);data=json.loads(Path(snapshot).read_text())
 if data.get('formatVersion')!=1 or set(data.get('tables',{}))!=set(TABLES):raise ValueError('Unsupported reviewed-state snapshot')
 if digest(encode(data['tables']))!=data.get('contentHash'):raise ValueError('Reviewed-state snapshot hash mismatch')
 if destination.exists():raise ValueError('Destination exists; choose a new database path. Runtime data will not be overwritten.')
 db=Database(destination)
 with db.connection() as c:
  actual={r['id']:claim_hash(json.loads(r['payload'])) for r in c.execute('SELECT id,payload FROM milestones')}
  if actual!=data['originalClaimHashes']:raise ValueError('Original milestone corpus differs from snapshot; explicit migration required')
  c.executescript(AUDIT_SCHEMA+ROLE_SCHEMA)
 with db.connection(write=True) as c:
  for table in TABLES:
   columns=[r['name'] for r in c.execute('PRAGMA table_info('+table+')')]
   if columns!=data['tables'][table]['columns']:raise ValueError('Schema mismatch for '+table)
  for table in reversed(TABLES):c.execute('DELETE FROM '+table)
  for table in TABLES:
   entry=data['tables'][table];marks=','.join('?' for _ in entry['columns'])
   c.executemany('INSERT INTO '+table+' VALUES ('+marks+')',entry['rows'])
  if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Restored records violate foreign keys')
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored database integrity check failed')
 return db

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True,type=Path,help='A new database filename; existing paths are refused.');p.add_argument('--snapshot',default=SNAPSHOT,type=Path);a=p.parse_args()
 d=restore(a.db,a.snapshot);print('Restored reviewed project state to '+str(d.path.resolve()))
