"""Explicit thematic review of the original unconnected milestones. No legacy edges.
Batch files are human-readable authored decisions; no keyword-based link generation.
"""
from pathlib import Path
import json,hashlib,runpy,collections
ROOT=Path(__file__).resolve().parents[1];REVIEW=ROOT/'research/connection-review'
BASE=json.loads((REVIEW/'baseline-tree.json').read_text());COLLECTION=json.loads((ROOT/'web/data/milestones.json').read_text());M={m['id']:m for m in COLLECTION['milestones']};REMAINING=json.loads((REVIEW/'baseline-remaining.json').read_text());R={m['id'] for m in REMAINING}
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def sha(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
class Batch:
 def __init__(self,id,fields):self.id=id;self.fields=fields;self.edges=[];self.unresolved={};self.rejected=[];self.branches=[]
 def a(self,src,dst,mechanism,limit,kind='accelerator',confidence='low',group=None):
  assert src in M and dst in M and src!=dst
  self.edges.append(dict(id=f'EXP-{self.id}-{len(self.edges)+1:03}',fromId=src,toId=dst,kind=kind,epistemicStatus='editorial-hypothesis',confidence=confidence,confidenceMeaning='Qualitative editorial confidence in conceptual fit only; not a measured probability or scientific validation.',rationale=mechanism,uncertainty=limit,provenance={'origin':'New remaining-collection review; interpreted directly from original milestone descriptions, not the legacy prerequisites.','review':'Mechanism and scope inspected against both original entries; conceptual hypothesis only.','sourceMilestones':[dict(id=i,workbook=M[i]['provenance']['workbook'],sheet='Master Table',row=M[i]['provenance']['row'],description=M[i]['description']) for i in [src,dst]],'reviewedAt':'2026-10-30','batch':self.id},resultIds=[],alternativeGroup=group))
 def u(self,id,reason,category='no-justified-link'):
  assert id in R and M[id]['field'] in self.fields,id
  self.unresolved[id]={'reason':reason,'category':category}
 def reject(self,src,dst,reason):self.rejected.append(dict(fromId=src,toId=dst,reason=reason))
 def branch(self,id,title,ids):self.branches.append(dict(id=id,title=title,nodeIds=ids))
 def save(self):
  target=REVIEW/'batches'/f'{self.id}.json'
  record=dict(id=self.id,fields=self.fields,reviewedIds=[m['id'] for m in REMAINING if m['field'] in self.fields],edges=self.edges,unresolved=self.unresolved,rejectedCandidates=self.rejected,branches=self.branches)
  target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');return record
if __name__=='__main__':
 import sys
 for arg in sys.argv[1:]:runpy.run_path(arg,run_name='__curation__')

def assemble():
 batches=[json.loads(p.read_text()) for p in sorted((REVIEW/'batches').glob('*.json'))]
 assert batches,'No batches'
 edges=list(BASE['edges']);branches=list(BASE['branches']);reviewed={};unresolved={};rejected=[];retired=[]
 for b in batches:
  for id in b['reviewedIds']:
   assert id not in reviewed,'Milestone reviewed in overlapping thematic batches';reviewed[id]=b['id']
  edges+=b['edges'];branches+=b['branches'];unresolved.update(b['unresolved']);rejected+=b['rejectedCandidates'];retired+=b.get('retiredEdges',[])
 retiredIds={r['id'] for r in retired};edges=[e for e in edges if e['id'] not in retiredIds]
 assert not retiredIds & {e['id'] for e in BASE['edges']},'Original links must be preserved'
 assert len({e['id'] for e in edges})==len(edges)
 assert len({(e['fromId'],e['toId']) for e in edges})==len(edges),'Duplicate directional relationship'
 reviews=[];connected={id for e in edges for id in [e['fromId'],e['toId']]}
 for position,m in enumerate(REMAINING):
  id=m['id']
  if id not in reviewed:continue
  incident=[e for e in edges if id in [e['fromId'],e['toId']]]
  if incident:
   decision={'disposition':'connected-hypothesis','reason':'Specific candidate mechanism: '+incident[0]['rationale'],'edgeIds':[e['id'] for e in incident]}
  else:
   assert id in unresolved,f'Missing individual disposition: {id} {m["title"]}'
   decision={'disposition':'equivalence-only' if unresolved[id]['category']=='source-equivalence' else 'unresolved','reason':unresolved[id]['reason'],'category':unresolved[id]['category'],'edgeIds':[]}
  reviews.append(dict(milestoneId=id,batch=reviewed[id],reviewedAt='2026-10-30',sourceHash=sha(m),reviewLevel='Editorial conceptual review; no scientific validation claimed.',**decision))
 summary={'initialUnconnected':546,'reviewed':len(reviews),'remainingToReview':546-len(reviews),'reviewedUnconnected':sum(r['disposition']!='connected-hypothesis' for r in reviews),'connectedNodes':len(connected),'unconnectedNodes':660-len(connected),'connectedFields':len({M[id]['field'] for id in connected}),'edgeCount':len(edges),'types':dict(collections.Counter(e['kind'] for e in edges)),'rejectedCandidateCount':len(rejected),'retiredProposals':len(retired)}
 tree=dict(BASE,version='connections-546-'+batches[-1]['id'],edges=edges,branches=branches,connectionReviews=reviews,reviewSummary=summary,reviewedCandidatesRejected=rejected)
 tree['policy']=dict(BASE['policy'],scope='The original milestone tree with an explicit review of the remaining collection. All arrows remain scoped editorial hypotheses; no achievements, dates or established prerequisites are inferred.')
 tree['policy']['types']['feedback']='Possible iterative contribution in a return direction, not a prerequisite or a promised chronological stage.'
 patch={'version':tree['version'],'title':'Connection review: '+batches[-1]['id'],'sourceHashes':{id:sha(M[id]) for id in M},'edges':[e for b in batches for e in b['edges'] if e['id'] not in retiredIds],'retiredEdges':retired,'branches':[b for batch in batches for b in batch['branches']],'reviews':reviews,'metadata':{k:v for k,v in tree.items() if k not in ['edges','branches','connectionReviews']},'summary':summary}
 (REVIEW/'current-patch.json').write_text(json.dumps(patch,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'web/data/tree.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,indent=2));return patch
