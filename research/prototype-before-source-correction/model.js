export const statuses=['observed','partial','forecast'];
export const clone=x=>JSON.parse(JSON.stringify(x));
export function safeUrl(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
export function gate(node,achieved){
 if(!node.routes.length) return {state:'unmodeled',routes:[]};
 const routes=node.routes.map(r=>({...r,met:r.all.every(id=>achieved.has(id)),missing:r.all.filter(id=>!achieved.has(id))}));
 return {state:routes.some(r=>r.met)?'route-ready':'blocked',routes};
}
export function edges(graph){return [...graph.nodes.flatMap(n=>n.routes.flatMap(r=>r.all.map(fromId=>({id:`${r.id}:${fromId}`,fromId,toId:n.id,kind:n.routes.length>1?'alternative':'required',...r})))),...graph.accelerators];}
export function validateGraph(g){
 if(!g||!Array.isArray(g.nodes)||!Array.isArray(g.sources)||!Array.isArray(g.accelerators)||!Array.isArray(g.openQuestions))throw Error('Invalid graph');
 const ids=new Set(g.nodes.map(n=>n.id)),sources=new Set(g.sources.map(s=>s.id));
 if(ids.size!==g.nodes.length||sources.size!==g.sources.length)throw Error('Duplicate stable ID');
 function refs(list){if(!Array.isArray(list)||!list.length||list.some(id=>!sources.has(id)))throw Error('Missing source provenance');}
 for(const s of g.sources)if(!safeUrl(s.url))throw Error('Invalid source URL');
 const adjacency=new Map(g.nodes.map(n=>[n.id,[]])); const routeIds=new Set();
 for(const n of g.nodes){
  if(!n.id||!n.title||!n.criteria||!n.uncertainty||!statuses.includes(n.status)||!['AI','Robotics','Materials','Longevity'].includes(n.domain)||!Number.isInteger(n.stage)||n.stage<0||n.stage>4||!Array.isArray(n.routes))throw Error('Invalid milestone');
  if(n.forecast&&(!n.forecast.window||!n.forecast.basis))throw Error('Forecast needs basis');
  refs(n.sourceIds);
  for(const r of n.routes){
   if(!r.id||routeIds.has(r.id)||!r.label||!Array.isArray(r.all)||!r.all.length||new Set(r.all).size!==r.all.length||!r.rationale||!r.uncertainty)throw Error('Invalid prerequisite route');
   routeIds.add(r.id);refs(r.sourceIds);
   for(const from of r.all){if(!ids.has(from))throw Error(`Missing milestone ${from}`);adjacency.get(n.id).push(from);}
  }
 }
 for(const a of g.accelerators){if(!ids.has(a.fromId)||!ids.has(a.toId)||a.fromId===a.toId||!a.rationale||!a.uncertainty)throw Error('Invalid accelerator');refs(a.sourceIds);}
 for(const q of g.openQuestions)if(!ids.has(q.target)||!q.reason)throw Error('Invalid unresolved concept');
 const active=new Set(),done=new Set();
 function visit(id){if(active.has(id))throw Error('Required dependency cycle (including alternative routes)');if(done.has(id))return;active.add(id);for(const next of adjacency.get(id))visit(next);active.delete(id);done.add(id);}
 for(const id of ids)visit(id);return true;
}
export function applyRevision(graph,revision){
 const g=clone(graph);const {event,change}=revision;
 if(!event||!event.id||!event.title?.trim()||!event.announcement?.trim()||!safeUrl(event.url)||!/^\d{4}-\d{2}-\d{2}$/.test(event.date)||!event.reviewer?.trim()||!change?.rationale?.trim()||!change?.uncertainty?.trim())throw Error('Event, reviewer, source, rationale and uncertainty are required');
 const n=g.nodes.find(n=>n.id===change.targetId);if(!n)throw Error('Unknown target');
 const source={id:event.id,title:event.title,url:event.url,published:event.date,scope:event.announcement,checkedAt:revision.createdAt,verification:`Manually reviewed by ${event.reviewer}; independent verification not automated`};
 if(g.sources.some(s=>s.id===source.id))throw Error('Duplicate event ID');g.sources.push(source);
 if(change.kind==='status'){
  if(!statuses.includes(change.status))throw Error('Invalid evidence status');
  if(change.status==='observed'&&!change.criteriaConfirmed)throw Error('Observed requires explicit criteria confirmation');
  n.status=change.status;n.sourceIds.push(source.id);
 }else if(change.kind==='forecast'){
  if(!change.window?.trim())throw Error('Forecast window required');n.forecast={window:change.window.trim(),basis:change.rationale};n.sourceIds.push(source.id);
 }else if(change.kind==='route'){
  n.routes.push({id:`route-${event.id}`,label:change.label||'Reviewed proposed route',all:change.all||[],rationale:change.rationale,uncertainty:change.uncertainty,sourceIds:[source.id],review:'manual-hypothesis'});
 }else if(change.kind==='accelerator'){
  g.accelerators.push({id:`acc-${event.id}`,fromId:change.fromId,toId:n.id,kind:'accelerator',rationale:change.rationale,uncertainty:change.uncertainty,sourceIds:[source.id]});
 }else if(change.kind==='remove-route'){
  if(!n.routes.some(r=>r.id===change.routeId))throw Error('Unknown route');n.routes=n.routes.filter(r=>r.id!==change.routeId);
 }else throw Error('Unknown change kind');
 n.lastReview={eventId:source.id,rationale:change.rationale,uncertainty:change.uncertainty};validateGraph(g);return g;
}
export function reconstruct(base,revisions,count=revisions.length){
 if(!Number.isInteger(count)||count<0||count>revisions.length)throw Error('Invalid revision');
 let graph=clone(base);validateGraph(graph);
 for(let i=0;i<count;i++){const r=revisions[i];if(r.number!==i+1)throw Error('Revision sequence broken');graph=applyRevision(graph,r);}
 return graph;
}
export function compare(before,after){
 const nodes=after.nodes.filter(n=>JSON.stringify(n)!==JSON.stringify(before.nodes.find(b=>b.id===n.id)));
 const b=new Map(edges(before).map(e=>[e.id,e])),a=new Map(edges(after).map(e=>[e.id,e]));
 return {nodes,added: [...a.values()].filter(e=>!b.has(e.id)),removed:[...b.values()].filter(e=>!a.has(e.id)),sourcesAdded:after.sources.filter(s=>!before.sources.some(b=>b.id===s.id))};
}
export function validateStore(base,store){
 if(store.schemaVersion!==1||store.baseVersion!==base.asOf||!Array.isArray(store.revisions)||!Array.isArray(store.proposals))throw Error('Incompatible saved state');
 reconstruct(base,store.revisions);
 const seen=new Set();for(const p of store.proposals){if(!p.id||seen.has(p.id)||!['pending','accepted','rejected'].includes(p.state)||!p.event||!p.change)throw Error('Invalid proposal');seen.add(p.id);}
 return store;
}
