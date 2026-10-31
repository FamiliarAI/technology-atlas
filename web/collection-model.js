export function validateCollection(data,evidence){
 if(data?.schemaVersion!==3||!Array.isArray(data.milestones)||!Array.isArray(data.fields)||!Array.isArray(data.relationships)||!Array.isArray(data.evidenceAssociations))throw Error('Invalid milestone collection');
 const ids=new Set(),fields=new Set(data.fields.map(f=>f.name)),results=new Set(evidence.results.map(r=>r.id));
 if(fields.size!==data.fields.length)throw Error('Duplicate field');
 for(const m of data.milestones){
  if(!m.id||ids.has(m.id))throw Error('Missing or duplicate original ID');ids.add(m.id);
  if(!fields.has(m.field)||m.status!=='proposed-milestone'||m.achievementReview!=='not-assessed')throw Error('Original aspirations must remain proposed');
  if(['forecast','projectedYear','criteria','rawPrerequisites','routes'].some(k=>k in m))throw Error('Unreviewed forecast or legacy dependencies cannot enter collection');
  if(!m.title||typeof m.description!=='string'||typeof m.impact!=='string'||m.provenance?.sheet!=='Master Table'||!Number.isInteger(m.provenance?.row))throw Error('Missing original text or provenance');
 }
 for(const f of data.fields)if(f.count!==data.milestones.filter(m=>m.field===f.name).length)throw Error('Field count mismatch');
 for(const m of data.milestones)if(m.duplicateOf&&(!ids.has(m.duplicateOf)||m.duplicateOf===m.id))throw Error('Unresolved duplicate target');
 const associations=new Set();for(const a of data.evidenceAssociations){
  if(!a.id||associations.has(a.id)||!ids.has(a.milestoneId)||!results.has(a.resultId))throw Error('Invalid evidence association');associations.add(a.id);
  if(!['partial-evidence','related-evidence','qualification','challenging-evidence'].includes(a.kind)||!a.relevance||!a.boundary||!a.provenance?.basis)throw Error('Evidence relevance and finding must be separate');
 }
 const relations=new Set();for(const r of data.relationships){
  if(!r.id||relations.has(r.id)||!ids.has(r.fromId)||!ids.has(r.toId)||r.fromId===r.toId)throw Error('Invalid relationship reference');relations.add(r.id);
  if(r.epistemicStatus!=='hypothesis'||r.kind!=='accelerator'||!r.rationale||!r.uncertainty||!r.provenance?.origin||!r.resultIds?.length||r.resultIds.some(id=>!results.has(id)))throw Error('No established dependency support reviewed; proposed links need provenance and uncertainty');
 }
 return true;
}
export function matchingMilestones(data,{field='All fields',query='',evidenceOnly=false,duplicatesOnly=false}={}){
 const q=query.trim().toLocaleLowerCase(),attached=new Set(data.evidenceAssociations.map(a=>a.milestoneId));
 return data.milestones.filter(m=>(field==='All fields'||m.field===field)&&(!q||[m.id,m.field,m.title,m.description,m.impact].join(' ').toLocaleLowerCase().includes(q))&&(!evidenceOnly||attached.has(m.id))&&(!duplicatesOnly||m.duplicateOf));
}
export function focusContext(data,id,{showHypotheses=false}={}){
 if(!data.milestones.some(m=>m.id===id))throw Error('Unknown original milestone');
 return {milestone:data.milestones.find(m=>m.id===id),evidence:data.evidenceAssociations.filter(a=>a.milestoneId===id),upstream:showHypotheses?data.relationships.filter(r=>r.toId===id):[],downstream:showHypotheses?data.relationships.filter(r=>r.fromId===id):[],duplicates:data.milestones.filter(m=>m.id===data.milestones.find(m=>m.id===id).duplicateOf||m.duplicateOf===id)};
}
