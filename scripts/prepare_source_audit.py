"""Prepare exact source-preserving research assignments. Does not classify claims."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def prepare():
 c=json.loads((ROOT/'web/data/milestones.json').read_text());fields=c['fields'];assignments=[[],[],[]]
 for i,f in enumerate(fields):
  items=[dict(m,claimHash=hashlib.sha256(canonical({k:m[k] for k in ['id','title','description','impact']}).encode()).hexdigest()) for m in c['milestones'] if m['field']==f['name']]
  doc=(ROOT/f['sourcePath']).read_text();record={'batchId':f'field-{i+1:02}','field':f['name'],'citationLinkage':'Field bibliography unless original text explicitly assigns a citation to an innovation.','originalNotes':doc,'innovations':items}
  (ROOT/'research/source-audit/assignments'/f'field-{i+1:02}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');assignments[i%3].append(record['batchId'])
 (ROOT/'research/source-audit/assignments/workers.json').write_text(json.dumps(assignments,indent=2)+'\n')
 print(assignments)
if __name__=='__main__':prepare()
