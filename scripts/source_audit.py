"""Versioned per-innovation webpage evidence; no promotion of milestone achievements."""
import argparse,json,hashlib,re
from pathlib import Path
from urllib.parse import urlsplit
from database import Database,APIError,encode,now,ROOT
STATUSES={'goal-supported','partial-progress','demonstrated-capability','background-only','unsupported','inaccessible','contradicted'}
POSITIVE={'goal-supported','partial-progress','demonstrated-capability','background-only','contradicted'}
OUTCOMES={'retrieved','inaccessible','not-found','mismatch','irrelevant','search-only','not-checked'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS source_audit_queue(milestone_id TEXT PRIMARY KEY REFERENCES milestones(id),claim_hash TEXT NOT NULL,position INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('pending','agent-reviewed','reviewed','needs-review')),payload TEXT NOT NULL CHECK(json_valid(payload)),updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_audit_batches(id TEXT PRIMARY KEY,content_hash TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_audit_checks(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES source_audit_batches(id),source_id TEXT NOT NULL,original_url TEXT NOT NULL,resolved_url TEXT,outcome TEXT NOT NULL,origin TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),UNIQUE(batch_id,source_id));
CREATE TABLE IF NOT EXISTS source_audit_assessments(milestone_id TEXT PRIMARY KEY REFERENCES source_audit_queue(milestone_id),batch_id TEXT NOT NULL REFERENCES source_audit_batches(id),classification TEXT NOT NULL,review_state TEXT NOT NULL CHECK(review_state IN ('agent-reviewed','reviewed','needs-review')),payload TEXT NOT NULL CHECK(json_valid(payload)),review_payload TEXT NOT NULL CHECK(json_valid(review_payload)),updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_audit_evidence(id TEXT PRIMARY KEY,milestone_id TEXT NOT NULL REFERENCES source_audit_assessments(milestone_id),source_check_id TEXT NOT NULL REFERENCES source_audit_checks(id),classification TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE IF NOT EXISTS source_audit_history(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)),created_at TEXT NOT NULL);
'''
def claim_hash(m):return hashlib.sha256(encode({k:m[k] for k in ['id','title','description','impact']}).encode()).hexdigest()
def fingerprint(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def initialize(database):
 with database.connection() as c:c.executescript(SCHEMA)
 with database.connection(write=True) as c:
  for r in c.execute('SELECT id,position,payload FROM milestones ORDER BY position').fetchall():
   m=json.loads(r['payload']);h=claim_hash(m);old=c.execute('SELECT claim_hash FROM source_audit_queue WHERE milestone_id=?',(r['id'],)).fetchone()
   if old and old[0]!=h:raise APIError(409,'Original claim changed; explicit re-review required: '+r['id'])
   payload={'milestoneId':m['id'],'title':m['title'],'description':m['description'],'impact':m['impact'],'candidateOriginalUrls':m['originalSourceLinks'],'citationLinkage':'Original field bibliography; not independently assigned proof for this innovation.'}
   c.execute('INSERT OR IGNORE INTO source_audit_queue VALUES (?,?,?,?,?,?)',(m['id'],h,r['position'],'pending',encode(payload),now()))
  revision='source-proof-audit-v1'
  c.execute('INSERT OR IGNORE INTO revisions(scope,original_id,position,payload,created_at) VALUES (?,?,?,?,?)',('database',revision,0,encode({'id':revision,'title':'Per-innovation webpage evidence audit initialized','date':now()[:10],'description':'Durable queue for all original innovations. Pending is not verified. Existing sources, tree and submissions preserved.'}),now()))
 return snapshot(database)
def url(value):
 if not isinstance(value,str):return False
 p=urlsplit(value)
 return p.scheme in {'http','https'} and bool(p.hostname) and not p.username and not p.password and not any(x.isspace() for x in value)
def validate(batch,assign):
 if batch.get('batchId')!=assign['batchId'] or batch.get('field')!=assign['field']:raise APIError(400,'Assignment identity mismatch')
 expected={m['id']:m for m in assign['innovations']};items=batch.get('innovations',[])
 if len(items)!=len(expected) or {m['milestoneId'] for m in items}!=set(expected):raise APIError(400,'Every assigned innovation must appear exactly once')
 sources=batch.get('sourceChecks',[]);by={s['id']:s for s in sources}
 if len(by)!=len(sources):raise APIError(400,'Duplicate source identifiers')
 for s in sources:
  if not url(s.get('originalUrl')) or (s.get('resolvedUrl') and not url(s['resolvedUrl'])):raise APIError(400,'Invalid source URL')
  if s.get('outcome') not in OUTCOMES or s.get('origin') not in {'original-notes','new-primary'}:raise APIError(400,'Invalid source outcome or origin')
  if len(s.get('excerpt','').split())>25:raise APIError(400,'Source excerpt exceeds short-quote limit')
  if s['outcome']=='retrieved' and not all(s.get(k) for k in ['title','accessedAt','locator','paraphrase','limitations','retrievalReference']):raise APIError(400,'Retrieved page requires inspectable passage and retrieval receipt')
  if s['origin']=='original-notes' and s['originalUrl'] not in {u for m in expected.values() for u in m['originalSourceLinks']} and s['originalUrl'] not in assign['originalNotes']:raise APIError(400,'New source mislabeled original')
 for item in items:
  if item.get('claimHash')!=expected[item['milestoneId']]['claimHash']:raise APIError(409,'Original claim hash mismatch')
  if item.get('overall') not in STATUSES or not item.get('summary') or not item.get('claims') or not item.get('searchLog'):raise APIError(400,'Individual assessment incomplete')
  for claim in item['claims']:
   if claim.get('classification') not in STATUSES or not all(claim.get(k) for k in ['claim','scope','limitations']):raise APIError(400,'Claim component incomplete')
   if any(id not in by for id in claim.get('sourceIds',[])):raise APIError(400,'Unknown claim source')
   if claim['classification'] in POSITIVE and not any(by[id]['outcome']=='retrieved' for id in claim.get('sourceIds',[])):raise APIError(400,'Positive claim component lacks read source')
  for evidence in item.get('evidence',[]):
   source=by.get(evidence.get('sourceId'))
   if not source or evidence.get('classification') not in STATUSES:raise APIError(400,'Unknown evidence source/classification')
   if evidence['classification'] in POSITIVE and (source['outcome']!='retrieved' or not all(evidence.get(k) for k in ['supportedClaim','locator','paraphrase','limitations'])):raise APIError(400,'Support requires read page and precise passage')
  if item['overall'] in POSITIVE and not any(e['classification'] in POSITIVE and by[e['sourceId']]['outcome']=='retrieved' for e in item.get('evidence',[])):raise APIError(400,'Classification lacks read supporting page')
 return True
def ingest(database,batch,review=None):
 assign=json.loads((ROOT/'research/source-audit/assignments'/f'{batch["batchId"]}.json').read_text());validate(batch,assign);initialize(database)
 # Explicit controller acceptance is required before agent findings appear as checked.
 revision=batch.get('revision',1)
 if not isinstance(revision,int) or revision<1:raise APIError(400,'Invalid source audit revision')
 record_id=batch['batchId'] if revision==1 else batch['batchId']+'-r'+str(revision)
 state='reviewed' if review and review.get('accepted') is True and review.get('notes') and review.get('reviewer') else 'agent-reviewed'
 h=fingerprint(batch);public_review={k:v for k,v in (review or {}).items() if k!='agentOriginal'}
 with database.connection(write=True) as c:
  old=c.execute('SELECT content_hash FROM source_audit_batches WHERE id=?',(record_id,)).fetchone()
  if old:
   if old[0]!=h:raise APIError(409,'Batch already exists with different content; retain version and audit correction explicitly')
   current_review=c.execute('SELECT review_state,review_payload FROM source_audit_assessments WHERE batch_id=? LIMIT 1',(record_id,)).fetchone()
   if state=='reviewed' and current_review and (current_review[0]!='reviewed' or json.loads(current_review[1])!=public_review):
    c.execute("UPDATE source_audit_assessments SET review_state='reviewed',review_payload=? WHERE batch_id=?",(encode(public_review),record_id))
    c.execute("UPDATE source_audit_queue SET state='reviewed',updated_at=? WHERE milestone_id IN (SELECT milestone_id FROM source_audit_assessments WHERE batch_id=?)",(now(),record_id))
    c.execute('INSERT INTO source_audit_history(batch_id,action,payload,created_at) VALUES (?,?,?,?)',(record_id,'controller-review',encode(review),now()))
   from source_roles import refresh
   refresh(c,{i['milestoneId'] for i in batch['innovations']})
   return {'alreadyImported':True,'batchId':batch['batchId'],'state':state}
  if revision==1 and c.execute('SELECT 1 FROM source_audit_assessments WHERE milestone_id=?',(batch['innovations'][0]['milestoneId'],)).fetchone():raise APIError(409,'Existing assessment requires an explicit correction revision')
  if revision>1:
   previous=c.execute('SELECT DISTINCT b.content_hash FROM source_audit_assessments a JOIN source_audit_batches b ON a.batch_id=b.id WHERE a.milestone_id IN ('+','.join('?' for _ in batch['innovations'])+')',tuple(i['milestoneId'] for i in batch['innovations'])).fetchall()
   if len(previous)!=1 or previous[0][0]!=batch.get('supersedesHash'):raise APIError(409,'Correction must name the exact previously reviewed batch hash')
  c.execute('INSERT INTO source_audit_batches VALUES (?,?,?,?)',(record_id,h,encode(batch),now()))
  for source in batch['sourceChecks']:
   c.execute('INSERT INTO source_audit_checks VALUES (?,?,?,?,?,?,?,?)',(record_id+':'+source['id'],record_id,source['id'],source['originalUrl'],source.get('resolvedUrl'),source['outcome'],source['origin'],encode(source)))
  for item in batch['innovations']:
   current=c.execute('SELECT claim_hash FROM source_audit_queue WHERE milestone_id=?',(item['milestoneId'],)).fetchone()
   if not current or current[0]!=item['claimHash']:raise APIError(409,'Runtime claim changed; refusing stale source review')
   if revision>1:c.execute('DELETE FROM source_audit_evidence WHERE milestone_id=?',(item['milestoneId'],))
   c.execute('INSERT INTO source_audit_assessments VALUES (?,?,?,?,?,?,?) ON CONFLICT(milestone_id) DO UPDATE SET batch_id=excluded.batch_id,classification=excluded.classification,review_state=excluded.review_state,payload=excluded.payload,review_payload=excluded.review_payload,updated_at=excluded.updated_at',(item['milestoneId'],record_id,item['overall'],state,encode(item),encode(public_review),now()))
   for i,evidence in enumerate(item.get('evidence',[])):
    c.execute('INSERT INTO source_audit_evidence VALUES (?,?,?,?,?)',(item['milestoneId']+':'+str(i),item['milestoneId'],record_id+':'+evidence['sourceId'],evidence['classification'],encode(evidence)))
   c.execute('UPDATE source_audit_queue SET state=?,updated_at=? WHERE milestone_id=?',(state,now(),item['milestoneId']))
  c.execute('INSERT INTO source_audit_history(batch_id,action,payload,created_at) VALUES (?,?,?,?)',(record_id,'import',encode({'hash':h,'verifier':batch['verifier'],'review':review,'state':state}),now()))
  from source_roles import refresh
  refresh(c,{i['milestoneId'] for i in batch['innovations']})
 return {'alreadyImported':False,'batchId':batch['batchId'],'state':state,'items':len(batch['innovations'])}
def snapshot(database,db=None):
 if db is None:
  with database.connection() as c:return snapshot(database,c)
 total=db.execute('SELECT COUNT(*) FROM milestones').fetchone()[0]
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='source_audit_queue'").fetchone():return {'summary':{'total':total,'checked':0,'pending':total,'agentReviewed':0,'revision':0,'statuses':{}},'innovations':[],'sources':[]}
 states={r[0]:r[1] for r in db.execute('SELECT state,COUNT(*) FROM source_audit_queue GROUP BY state')};statuses={r[0]:r[1] for r in db.execute("SELECT classification,COUNT(*) FROM source_audit_assessments WHERE review_state='reviewed' GROUP BY classification")}
 items=[dict(json.loads(r['payload']),reviewState=r['review_state'],controllerReview={k:v for k,v in json.loads(r['review_payload']).items() if k!='agentOriginal'},batchId=r['batch_id']) for r in db.execute('SELECT * FROM source_audit_assessments ORDER BY milestone_id')]
 sources=[dict(json.loads(r['payload']),checkId=r['id'],batchId=r['batch_id']) for r in db.execute('SELECT * FROM source_audit_checks WHERE batch_id IN (SELECT DISTINCT batch_id FROM source_audit_assessments) ORDER BY id')]
 from source_roles import assignments,summary as role_summary
 roles=assignments(db)
 for item in items:item['sourceRoles']=roles.get(item['milestoneId'])
 return {'summary':{'sourceRoles':role_summary(db),'total':total,'checked':states.get('reviewed',0),'pending':total-states.get('reviewed',0),'agentReviewed':states.get('agent-reviewed',0),'needsReview':states.get('needs-review',0),'revision':db.execute('SELECT COALESCE(MAX(seq),0) FROM source_audit_history').fetchone()[0],'statuses':statuses,'originalSourceChecks':sum(s['origin']=='original-notes' for s in sources),'newPrimarySourceChecks':sum(s['origin']=='new-primary' for s in sources)},'innovations':items,'sources':sources}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('result',nargs='?',type=Path);p.add_argument('--review',type=Path);a=p.parse_args();d=Database()
 print(json.dumps(ingest(d,json.loads(a.result.read_text()),json.loads(a.review.read_text()) if a.review else None) if a.result else initialize(d),ensure_ascii=False)[:3000])
