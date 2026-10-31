export function safeUrl(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null;}catch{return null;}}
const nonempty=v=>typeof v==='string'&&v.trim().length>0;
export function validateEvidence(data){
 if(data?.schemaVersion!==2||!nonempty(data.version)||!Array.isArray(data.domains)||!Array.isArray(data.results)||!Array.isArray(data.edges))throw Error('Invalid evidence dataset');
 if(data.edges.length)throw Error('Dependency edges require a separate direct-support review; this view has none');
 const ids=new Set(),sources=new Set();
 for(const r of data.results){
  if(ids.has(r.id))throw Error('Duplicate result ID');ids.add(r.id);
  if(!data.domains.includes(r.domain)||r.status!=='reported-result')throw Error('Unsupported result state');
  if(['forecast','criteria','routes','sourceEntryIds','projectedYear','stage'].some(k=>k in r))throw Error('Speculative milestone fields cannot appear as evidence');
  for(const k of ['id','title','kind','claim','scope','limitations'])if(!nonempty(r[k]))throw Error(`Missing result ${k}`);
  const s=r.source;if(!s||!safeUrl(s.url))throw Error('Missing safe primary-source URL');
  for(const k of ['id','title','published','dateLabel','locator','checkedAt','checkMethod','accessNote'])if(!nonempty(s[k]))throw Error(`Missing source ${k}`);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(s.published)||s.published>data.checkedAt)throw Error('Invalid or future publication date');
  if(sources.has(s.id))throw Error('Duplicate source ID in selected evidence set');sources.add(s.id);
  if(s.correction&&(!safeUrl(s.correction.url)||!nonempty(s.correction.note)))throw Error('Invalid correction provenance');
 }
 return true;
}
export function filterResults(data,{domain='All fields',query='',kind='all'}={}){
 const q=query.trim().toLocaleLowerCase();return data.results.filter(r=>(domain==='All fields'||r.domain===domain)&&(kind==='all'||r.kind===kind)&&(!q||[r.title,r.claim,r.scope,r.limitations,r.domain,r.source.title].join(' ').toLocaleLowerCase().includes(q)));
}
export function proposal(input){
 if(!nonempty(input.title)||!safeUrl(input.url)||!nonempty(input.summary)||!nonempty(input.limits))throw Error('Title, HTTPS source, summary and limitations are required');
 if([input.title,input.url,input.summary,input.limits].some(x=>x.length>12000))throw Error('Submission is too long');
 // Submissions are never accepted into the reviewed dataset by a browser action.
 return {id:input.id,title:input.title.trim(),url:safeUrl(input.url),summary:input.summary.trim(),limits:input.limits.trim(),state:'pending-source-review',createdAt:input.createdAt,...(input.milestoneId?{milestoneId:input.milestoneId}:{})};
}
export function validateDesk(value){
 if(value?.schemaVersion!==2||!Array.isArray(value.submissions))throw Error('Invalid research desk');
 const ids=new Set();for(const item of value.submissions){proposal(item);if(!item.id||ids.has(item.id)||!['pending-source-review','dismissed'].includes(item.state))throw Error('Invalid submission state');ids.add(item.id);}
 return value;
}
