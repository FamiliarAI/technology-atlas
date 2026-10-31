import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';import {validateTree,treeView,layoutTree} from '../web/tree-model.js';
const load=p=>JSON.parse(readFileSync(new URL(p,import.meta.url))),t=load('../web/data/tree.json'),c=load('../web/data/milestones.json'),e=load('../web/data/evidence.json'),base=load('../research/connection-review/baseline-tree.json'),remaining=load('../research/connection-review/baseline-remaining.json');
const canonical=x=>Array.isArray(x)?`[${x.map(canonical).join(',')}]`:x&&typeof x==='object'?`{${Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')}}`:JSON.stringify(x);
test('all 546 original gaps have individual source-preserving dispositions and every unconnected node has a reason',()=>{
 assert.equal(validateTree(t,c,e),true);assert.equal(t.connectionReviews.length,546);assert.deepEqual(new Set(t.connectionReviews.map(r=>r.milestoneId)),new Set(remaining.map(m=>m.id)));
 const connected=new Set(t.edges.flatMap(e=>[e.fromId,e.toId]));assert.equal(connected.size,462);assert.equal(t.edges.length,444);
 for(const r of t.connectionReviews){const m=c.milestones.find(m=>m.id===r.milestoneId);assert.equal(r.sourceHash,createHash('sha256').update(canonical(m)).digest('hex'));assert.ok(r.reason.length>35);assert.equal(r.disposition==='connected-hypothesis',connected.has(r.milestoneId));assert.deepEqual(new Set(r.edgeIds),new Set(t.edges.filter(e=>[e.fromId,e.toId].includes(r.milestoneId)).map(e=>e.id)));}
 for(const m of c.milestones.filter(m=>!connected.has(m.id)))assert.ok(t.connectionReviews.find(r=>r.milestoneId===m.id)?.reason);
 for(const original of base.edges)assert.deepEqual(t.edges.find(e=>e.id===original.id),original);
 assert.equal(t.edges.filter(e=>e.kind==='required').length,0);assert.equal(t.reviewSummary.remainingToReview,0);assert.equal(t.reviewedCandidatesRejected.length,40);
});
test('expanded branches and all fields remain navigable without overlapping nodes or unbounded default views',()=>{
 for(const options of [...t.branches.map(b=>({branch:b.id})),...c.fields.map(f=>({field:f.name})),...c.milestones.map(n=>({focusId:n.id,depth:2}))]){
  const v=treeView(t,c,options),l=layoutTree(v);assert.ok(v.nodes.length<=48);assert.ok(v.edges.every(e=>e.kind==='feedback'||l.positions.get(e.fromId).x<l.positions.get(e.toId).x));
  if(options.field){const represented=new Set([...v.nodes,...v.unmapped,...v.outside].map(n=>n.id));for(const n of c.milestones.filter(n=>n.field===options.field))assert.ok(represented.has(n.id));}
  const boxes=[...l.positions.values()];for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];assert.ok(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y);}
 }
});
test('explicit feedback renders while an ordinary reverse dependency still fails',()=>{
 assert.equal(t.edges.filter(e=>e.kind==='feedback').length,8);const copy=structuredClone(t),feedback=copy.edges.find(e=>e.kind==='feedback');feedback.kind='required';feedback.requiredScope='Synthetic test';assert.throws(()=>validateTree(copy,c,e),/cycle/);
});
