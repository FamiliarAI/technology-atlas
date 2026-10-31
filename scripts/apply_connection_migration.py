"""Explicit, transactional, idempotent content migration. Never reseeds live data."""
from pathlib import Path
import json,argparse
from database import Database,DEFAULT_DB,encode,digest,now,APIError

def content_hash(value):return digest(encode(value))
def validate_graph(db):
 nodes={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM milestones')}
 edges=[json.loads(r[0]) for r in db.execute("SELECT payload FROM relationships WHERE layer='tree'")]
 degree={id:0 for id in nodes};children={id:[] for id in nodes}
 for edge in edges:
  if edge['kind'] not in {'enabling','accelerator','alternative-route','feedback','required'}:raise APIError(400,'Unknown relationship type')
  if edge['fromId']==edge['toId']:raise APIError(400,'Self relationship')
  for id in [edge['fromId'],edge['toId']]:
   source=next((p for p in edge['provenance']['sourceMilestones'] if p['id']==id),None)
   if not source or source['description']!=nodes[id]['description'] or source['row']!=nodes[id]['provenance']['row']:raise APIError(409,'Relationship source text mismatch')
  if edge['kind']!='feedback':degree[edge['toId']]+=1;children[edge['fromId']].append(edge['toId'])
 queue=[id for id in degree if degree[id]==0];seen=0
 while queue:
  id=queue.pop();seen+=1
  for target in children[id]:
   degree[target]-=1
   if degree[target]==0:queue.append(target)
 if seen!=len(nodes):raise APIError(409,'Ordinary dependency cycle; use only explicitly justified feedback')

def apply(database,patch):
 version=patch['version'];fingerprint=content_hash(patch)
 with database.connection(write=True) as db:
  prior=db.execute("SELECT payload FROM revisions WHERE scope='content' AND original_id=?",(version,)).fetchone()
  if prior:
   if json.loads(prior[0]).get('patchHash')!=fingerprint:raise APIError(409,'Content version already exists with a different patch')
   return {'alreadyApplied':True,'version':version}
  milestones={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM milestones')}
  if set(milestones)!=set(patch['sourceHashes']):raise APIError(409,'Original milestone identities changed; review before migrating')
  for id,m in milestones.items():
   if content_hash(m)!=patch['sourceHashes'][id]:raise APIError(409,'Original source content changed for '+id+'; migration will not overwrite it')
  removed=0
  for retired in patch.get('retiredEdges',[]):
   if not retired['id'].startswith('EXP-'):raise APIError(409,'Only explicitly reviewed new proposals can be retired')
   row=db.execute("SELECT payload FROM relationships WHERE layer='tree' AND id=?",(retired['id'],)).fetchone()
   if row:
    if json.loads(row[0])!=retired['expectedPayload']:raise APIError(409,'Retired proposal was changed; refusing to delete it')
    db.execute("DELETE FROM relationship_evidence WHERE layer='tree' AND relationship_id=?",(retired['id'],))
    db.execute("DELETE FROM relationships WHERE layer='tree' AND id=?",(retired['id'],));removed+=1
  position=db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM relationships WHERE layer='tree'").fetchone()[0];added=0
  for edge in patch['edges']:
   row=db.execute("SELECT payload FROM relationships WHERE layer='tree' AND id=?",(edge['id'],)).fetchone()
   if row:
    if json.loads(row[0])!=edge:raise APIError(409,'Existing relationship conflicts: '+edge['id'])
    continue
   if db.execute("SELECT 1 FROM relationships WHERE layer='tree' AND from_id=? AND to_id=?",(edge['fromId'],edge['toId'])).fetchone():raise APIError(409,'Another relationship already uses this pair')
   if edge['epistemicStatus']!='editorial-hypothesis' or not edge['rationale'] or not edge['uncertainty']:raise APIError(400,'Relationship needs scoped hypothesis reasoning')
   db.execute('INSERT INTO relationships VALUES (?,?,?,?,?,?,?)',(edge['id'],'tree',edge['fromId'],edge['toId'],edge['kind'],position,encode(edge)));position+=1;added+=1
   for i,id in enumerate(edge['resultIds']):db.execute('INSERT INTO relationship_evidence VALUES (?,?,?,?)',('tree',edge['id'],id,i))
  position=db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM branches').fetchone()[0]
  for branch in patch['branches']:
   original=db.execute('SELECT payload FROM branches WHERE id=?',(branch['id'],)).fetchone();payload={k:v for k,v in branch.items() if k!='nodeIds'}
   if original:
    ids=[r[0] for r in db.execute('SELECT milestone_id FROM branch_nodes WHERE branch_id=? ORDER BY position',(branch['id'],))]
    if json.loads(original[0])!=payload or ids!=branch['nodeIds']:raise APIError(409,'Existing branch conflicts: '+branch['id'])
    continue
   db.execute('INSERT INTO branches VALUES (?,?,?)',(branch['id'],position,encode(payload)));position+=1
   for i,id in enumerate(branch['nodeIds']):db.execute('INSERT INTO branch_nodes VALUES (?,?,?)',(branch['id'],id,i))
  validate_graph(db)
  for i,review in enumerate(patch['reviews']):
   db.execute('INSERT INTO connection_reviews VALUES (?,?,?,?) ON CONFLICT(milestone_id) DO UPDATE SET revision_id=excluded.revision_id,position=excluded.position,payload=excluded.payload',(review['milestoneId'],version,i,encode(review)))
  metadata=json.loads(db.execute("SELECT metadata FROM documents WHERE name='tree'").fetchone()[0]);metadata.update(patch['metadata']);db.execute("UPDATE documents SET metadata=? WHERE name='tree'",(encode(metadata),))
  record={'id':version,'date':now()[:10],'title':patch['title'],'description':'Expanded conceptual relationship review. Original milestone and user-submission records unchanged.','patchHash':fingerprint,'summary':patch['summary'],'addedEdgeIds':[e['id'] for e in patch['edges']],'reviewDecisions':patch['reviews'],'retiredEdges':patch.get('retiredEdges',[])}
  db.execute('INSERT INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('content',version,0,encode(record),now()))
  if db.execute('PRAGMA foreign_key_check').fetchone():raise APIError(409,'Foreign-key validation failed')
  return {'alreadyApplied':False,'version':version,'edgesAdded':added,'edgesRemoved':removed,**patch['summary']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('patch',type=Path);p.add_argument('--db',type=Path,default=DEFAULT_DB);a=p.parse_args();print(json.dumps(apply(Database(a.db),json.loads(a.patch.read_text())),indent=2))
