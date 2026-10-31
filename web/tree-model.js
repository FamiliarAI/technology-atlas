export const edgeTypes=['enabling','accelerator','alternative-route','feedback','required'];
export function validateTree(tree,collection,evidence){
 if(tree?.schemaVersion!==1||!Array.isArray(tree.edges)||!Array.isArray(tree.branches))throw Error('Invalid tree');
 const nodes=new Map(collection.milestones.map(n=>[n.id,n])),results=new Set(evidence.results.map(r=>r.id)),ids=new Set(),pairs=new Set();
 for(const e of tree.edges){
  const pair=`${e.fromId}:${e.toId}`;
  if(!e.id||ids.has(e.id)||pairs.has(pair)||!nodes.has(e.fromId)||!nodes.has(e.toId)||e.fromId===e.toId)throw Error('Invalid edge identity or reference');ids.add(e.id);pairs.add(pair);
  if(!edgeTypes.includes(e.kind)||e.epistemicStatus!=='editorial-hypothesis'||!['low','moderate'].includes(e.confidence)||!e.rationale||!e.uncertainty||!e.confidenceMeaning)throw Error('Relationship requires type, hypothesis status, confidence and limitations');
  if(!e.provenance?.origin||!e.provenance.review||e.provenance.sourceMilestones?.length!==2)throw Error('Missing relationship provenance');
  for(const id of [e.fromId,e.toId]){const p=e.provenance.sourceMilestones.find(p=>p.id===id),m=nodes.get(id);if(!p||p.row!==m.provenance.row||p.description!==m.description)throw Error('Relationship source text mismatch');}
  if(!Array.isArray(e.resultIds)||e.resultIds.some(id=>!results.has(id)))throw Error('Unknown contextual research');
  if(e.kind==='alternative-route'&&!e.alternativeGroup)throw Error('Alternative research route needs a group');
  if(e.kind==='required'&&!e.requiredScope)throw Error('Required edges need an explicit scope');
 }
 // Ordinary arrows must remain acyclic. Explicit feedback is excluded from prerequisite ranking.
 const idsInTree=new Set(tree.edges.flatMap(e=>[e.fromId,e.toId]));topologicalLayers([...idsInTree],tree.edges.filter(e=>e.kind!=='feedback'));
 for(const b of tree.branches)if(!b.id||!b.title||!b.nodeIds.length||b.nodeIds.some(id=>!nodes.has(id)))throw Error('Invalid branch');
 return true;
}
export function lineage(tree,id,direction='both'){
 const found=new Set([id]),queue=[id];while(queue.length){const current=queue.shift();for(const e of tree.edges){const next=(direction!=='downstream'&&e.toId===current)?e.fromId:(direction!=='upstream'&&e.fromId===current)?e.toId:null;if(next&&!found.has(next)){found.add(next);queue.push(next);}}}return found;
}
export function treeView(tree,collection,{branch='manipulation',field=null,focusId=null,depth=2}={}){
 const all=new Map(collection.milestones.map(m=>[m.id,m])),connected=new Set(tree.edges.flatMap(e=>[e.fromId,e.toId]));let ids;
 if(focusId){
  if(!all.has(focusId))throw Error('Unknown focus milestone');ids=new Set([focusId]);
  if(depth==='all'){ids=new Set([...lineage(tree,focusId,'upstream'),...lineage(tree,focusId,'downstream')]);}
  else {for(const direction of ['upstream','downstream']){let frontier=new Set([focusId]);for(let i=0;i<depth;i++){const next=new Set();for(const e of tree.edges){if(direction==='upstream'&&frontier.has(e.toId))next.add(e.fromId);if(direction==='downstream'&&frontier.has(e.fromId))next.add(e.toId);}for(const id of next)ids.add(id);frontier=next;}}}
 }else if(field){ids=new Set(collection.milestones.filter(m=>m.field===field).map(m=>m.id));const seeds=new Set(ids);for(const e of tree.edges)if(seeds.has(e.fromId)||seeds.has(e.toId)){ids.add(e.fromId);ids.add(e.toId);}}
 else{const b=tree.branches.find(b=>b.id===branch);if(!b)throw Error('Unknown branch');ids=new Set(b.nodeIds);}
 const scopeIds=new Set(ids),limit=depth==='all'?96:48;
 // Keep the requested field/focus first; bound contextual expansion for readable navigation.
 const priority=focusId?[focusId]:field?collection.milestones.filter(m=>m.field===field).map(m=>m.id):[];
 const ordered=[...new Set([...priority,...ids])].filter(id=>ids.has(id));
 ids=new Set(ordered.slice(0,limit));
 const edges=tree.edges.filter(e=>ids.has(e.fromId)&&ids.has(e.toId));const shown=new Set(edges.flatMap(e=>[e.fromId,e.toId]));
 if(focusId&&!shown.size)shown.add(focusId);
 const unmapped=[...ids].filter(id=>!connected.has(id)).map(id=>all.get(id));const outside=[...ids].filter(id=>connected.has(id)&&!shown.has(id)).map(id=>all.get(id));
 return {nodes:[...shown].map(id=>all.get(id)),edges,unmapped,outside,scopeCount:scopeIds.size,omittedNodes:scopeIds.size-ids.size};
}
export function topologicalLayers(nodeIds,edges){
 const degree=new Map(nodeIds.map(id=>[id,0])),next=new Map(nodeIds.map(id=>[id,[]])),layer=new Map(nodeIds.map(id=>[id,0]));
 for(const e of edges){if(!degree.has(e.fromId)||!degree.has(e.toId))throw Error('Layout edge points outside view');degree.set(e.toId,degree.get(e.toId)+1);next.get(e.fromId).push(e.toId);}
 const queue=nodeIds.filter(id=>degree.get(id)===0).sort();let visited=0;
 while(queue.length){const id=queue.shift();visited++;for(const to of next.get(id)){layer.set(to,Math.max(layer.get(to),layer.get(id)+1));degree.set(to,degree.get(to)-1);if(!degree.get(to))queue.push(to);}}
 if(visited!==nodeIds.length)throw Error('Dependency cycle; no valid upstream/downstream layering');return layer;
}
export function layoutTree(view){
 const layers=topologicalLayers(view.nodes.map(n=>n.id),view.edges.filter(e=>e.kind!=='feedback')),positions=new Map(),cols=new Map();
 for(const n of view.nodes){const l=layers.get(n.id);if(!cols.has(l))cols.set(l,[]);cols.get(l).push(n);}
 const nodeWidth=255,nodeHeight=120,gapX=100,gapY=35,pad=45;
 const rows=Math.max(1,...[...cols.values()].map(c=>c.length)),height=rows*(nodeHeight+gapY)+pad*2;
 for(const [col,nodes] of [...cols.entries()].sort((a,b)=>a[0]-b[0])){
  nodes.sort((a,b)=>{const y=id=>{const parents=view.edges.filter(e=>e.toId===id).map(e=>positions.get(e.fromId)?.y).filter(y=>y!==undefined);return parents.length?parents.reduce((a,b)=>a+b,0)/parents.length:0;};return y(a.id)-y(b.id)||a.field.localeCompare(b.field)||a.id.localeCompare(b.id);});
  const offset=(height-(nodes.length*(nodeHeight+gapY)-gapY))/2;
  nodes.forEach((n,i)=>positions.set(n.id,{x:pad+col*(nodeWidth+gapX),y:offset+i*(nodeHeight+gapY),width:nodeWidth,height:nodeHeight,layer:col}));
 }
 return {positions,width:Math.max(1,...layers.values())*(nodeWidth+gapX)+nodeWidth+pad*2,height,layers};
}
