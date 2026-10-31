"""Persist source purpose independently of source origin; never infer proposal authorship."""
import json,argparse
from pathlib import Path
from database import Database,encode,now

SCHEMA='''CREATE TABLE IF NOT EXISTS source_role_assignments(
 milestone_id TEXT PRIMARY KEY REFERENCES milestones(id),
 claim_hash TEXT NOT NULL,
 audit_batch_id TEXT REFERENCES source_audit_batches(id),
 payload TEXT NOT NULL CHECK(json_valid(payload)),updated_at TEXT NOT NULL);'''
PROGRESS={'partial-progress','demonstrated-capability'}
# Role decisions apply only to these immutable audited source versions; audit labels stay intact.
CONTEXT_DECISIONS={
 ('ACT-02:0','field-01:s8'):'Proposed model-development framework, not an evaluated demonstrated result.',
 ('ACT-07:0','field-01:s8'):'Proposed fairness framework, not demonstrated fair performance.',
 ('ACT-07:1','field-01:s11'):'Survey of fairness metrics and incompatible definitions.',
 ('AER-02:0','field-02:s7'):'Aircraft shaping design aim; this passage does not report a measured sonic-boom result.',
 ('BME-10:0','field-09-r2:s8'):'Safety-mechanism and failure summary, not demonstrated safe oxygen-carrier performance.',
 ('CIV-07:0','field-15:s9'):'Design-method review and research gaps, not a demonstrated collapse-arrest mechanism.',
 ('INF-09:0','field-32:s14'):'Clinical trial stopped for insufficient efficacy; retained as a research outcome, not demonstrated therapeutic progress.',
 ('PET-03:0','field-52-r2:s3'):'Tested catalyst did not outperform the comparator; no demonstrated upgrading advantage.',
 ('PHY-03:0','field-54:s11'):'Review describes an unresolved explanation; no microscopic mechanism demonstrated.'}


def exists(c):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='source_role_assignments'").fetchone())
def refresh(c,ids=None):
 """Called in the same transaction as an explicit migration or audit correction."""
 if not exists(c):return 0
 from source_audit import claim_hash
 changed=[]
 for row in c.execute('SELECT id,payload FROM milestones ORDER BY position').fetchall():
  if ids is not None and row['id'] not in ids:continue
  m=json.loads(row['payload']);a=c.execute('SELECT * FROM source_audit_assessments WHERE milestone_id=?',(m['id'],)).fetchone();batch=a['batch_id'] if a else None
  sources={s['source_id']:dict(json.loads(s['payload']),checkId=s['id']) for s in c.execute('SELECT * FROM source_audit_checks WHERE batch_id=?',(batch,))} if batch else {}
  candidates=[]
  for link in m['originalSourceLinks']:
   s=next((s for s in sources.values() if s['origin']=='original-notes' and (s.get('originalCitationUrl') or s['originalUrl'])==link),None)
   candidates.append({'role':'proposal-source','attribution':'field-bibliography','origin':'original-notes','url':s['originalUrl'] if s else link,'recordedUrl':link,'sourceId':s['id'] if s else None,'sourceCheckId':s['checkId'] if s else None,'title':s.get('title') if s else None,'retrievalOutcome':s['outcome'] if s else 'not-checked'})
  r={'proposalAttribution':{'status':'unconfirmed','recordedIn':{'field':m['field'],'entryId':m['id']},'statement':'The proposal is preserved in the original field notes. Its exact innovation-specific webpage source has not been confirmed. These bibliography links were supplied for the field, not individually attributed to this proposal.'},'proposalSources':candidates,'progressEvidence':[],'contextEvidence':[],'completion':'not-established'}
  if a and a['review_state']=='reviewed':
   for e in c.execute('SELECT * FROM source_audit_evidence WHERE milestone_id=? ORDER BY id',(m['id'],)):
    ev=json.loads(e['payload']);s=next(s for s in sources.values() if s['checkId']==e['source_check_id'])
    reason=CONTEXT_DECISIONS.get((e['id'],s['checkId']))
    if not reason and s.get('sourceType') in {'review','journal-index'}:reason='Review or bibliographic record retained as context; this is not an inspected primary demonstration.'
    progress=ev['classification'] in PROGRESS and s['outcome']=='retrieved' and not reason
    r['progressEvidence' if progress else 'contextEvidence'].append(dict(ev,evidenceId=e['id'],sourceCheckId=s['checkId'],role='progress-evidence' if progress else 'audit-context',roleReason=reason or ('Reviewed scoped result; full milestone completion not established.' if progress else 'Research goal, background, negative finding or failed retrieval; not demonstrated progress.'),origin=s['origin']))
  old=c.execute('SELECT * FROM source_role_assignments WHERE milestone_id=?',(m['id'],)).fetchone();h=claim_hash(m)
  if old and old['payload']==encode(r) and old['claim_hash']==h and old['audit_batch_id']==batch:continue
  c.execute('INSERT INTO source_role_assignments VALUES (?,?,?,?,?) ON CONFLICT(milestone_id) DO UPDATE SET claim_hash=excluded.claim_hash,audit_batch_id=excluded.audit_batch_id,payload=excluded.payload,updated_at=excluded.updated_at',(m['id'],h,batch,encode(r),now()))
  changed.append({'milestoneId':m['id'],'previous':json.loads(old['payload']) if old else None,'current':r})
 if changed:c.execute('INSERT INTO source_audit_history(batch_id,action,payload,created_at) VALUES (?,?,?,?)',('source-roles-v1','source-role-refresh',encode({'policy':'Reviewed partial-progress/demonstrated-capability passages qualify only when they report a result: reviews/indexes and explicit version-bound design/null-result decisions remain context. Origin never assigns purpose or confirms proposal attribution.','changes':changed}),now()))
 return len(changed)
def backfill(database):
 from source_audit import initialize
 initialize(database)
 with database.connection() as c:c.executescript(SCHEMA)
 with database.connection(write=True) as c:return {'changed':refresh(c),'sourceRoles':summary(c)}
def summary(c):
 if not exists(c):return {'mapped':0,'confirmedProposalAttribution':0,'unconfirmedProposalAttribution':0,'withProgressEvidence':0,'progressEvidenceRows':0,'contextEvidenceRows':0,'proposalBibliographyLinks':0}
 rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM source_role_assignments')]
 return {'mapped':len(rows),'confirmedProposalAttribution':sum(r['proposalAttribution']['status']=='confirmed' for r in rows),'unconfirmedProposalAttribution':sum(r['proposalAttribution']['status']=='unconfirmed' for r in rows),'withProgressEvidence':sum(bool(r['progressEvidence']) for r in rows),'progressEvidenceRows':sum(len(r['progressEvidence']) for r in rows),'contextEvidenceRows':sum(len(r['contextEvidence']) for r in rows),'proposalBibliographyLinks':sum(len(r['proposalSources']) for r in rows)}
def assignments(c):return {r['milestone_id']:json.loads(r['payload']) for r in c.execute('SELECT milestone_id,payload FROM source_role_assignments')} if exists(c) else {}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path);a=p.parse_args();print(json.dumps(backfill(Database(a.db) if a.db else Database()),indent=2))
