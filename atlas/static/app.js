const $ = s => document.querySelector(s);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = url => {try {const u=new URL(url);return ['https:','http:'].includes(u.protocol)?u.href:'#';} catch{return '#';}};
let data, W=1200, H=660, field=null, query='', mode=innerWidth<700?'list':'map', selected=null, focusReturn=null, request=0, zoom=1, pan={x:0,y:0}, positions={}, drag=null, moved=false;
const sections=[['concept','Concept'],['significance','Significance'],['missing_breakthrough','Missing breakthrough'],['current_state','Current state'],['completion_criteria','Milestones'],['related_concepts','Related concepts']];
function visible(){return data.innovations.filter(i=>(!field||i.field===field)&&(!query||(`${i.id} ${i.title} ${i.search_text}`).toLowerCase().includes(query)));}
function draw(){
 const items=visible(),pad=n=>String(n).padStart(2,'0');$('#total').textContent=$('#footer-total').textContent=data.innovations.length;$('#field-total').textContent=data.fields.length;$('#field-range').textContent=`01—${pad(data.fields.length)}`;
 $('#fields').innerHTML=data.fields.map((f,n)=>`<button class="field ${field===f.id?'active':''}" style="--color:${f.color}" data-field="${f.id}" aria-pressed="${field===f.id}"><span class="field-code">${pad(n+1)} / ${f.id}</span><span class="arrow">↗</span><h2>${esc(f.name)}</h2><small>${data.innovations.filter(i=>i.field===f.id).length} innovations</small></button>`).join('');
 $('#fields').querySelectorAll('button').forEach(b=>b.onclick=()=>{field=field===b.dataset.field?null:b.dataset.field;zoom=1;pan={x:0,y:0};draw();});
 $('#result-count').textContent=`${String(items.length).padStart(2,'0')} INNOVATIONS / ${field?data.fields.find(f=>f.id===field).name.toUpperCase():'ALL FIELDS'}`;
 $('#map-mode').setAttribute('aria-pressed',mode==='map');$('#list-mode').setAttribute('aria-pressed',mode==='list');
 $('#map-wrap').hidden=mode!=='map'||!items.length;$('#list').hidden=mode!=='list'||!items.length;$('#empty').hidden=!!items.length;
 $('#list').innerHTML=items.map(i=>`<button class="result-card" data-id="${i.id}" style="--color:${data.fields.find(f=>f.id===i.field).color}"><span class="card-id">${i.id}</span><div><h3>${esc(i.title)}</h3><p>${esc(i.summary)}</p><div class="meta">${esc(data.fields.find(f=>f.id===i.field).name)} · ${i.milestone_count} MILESTONES · ${i.source_count} SOURCES</div></div><span class="card-arrow">↗</span></button>`).join('');
 $('#list').querySelectorAll('button').forEach(b=>b.onclick=()=>openItem(b.dataset.id));drawMap(items);
}
function wrap(text,width=25){const words=text.split(' '),lines=[''];for(const w of words){if((lines.at(-1)+' '+w).length>width)lines.push(w);else lines[lines.length-1]+=(lines.at(-1)?' ':'')+w;}return lines;}
function drawMap(items){
 const shown=new Set(items.map(i=>i.id));positions={};const cols=Math.ceil(Math.sqrt(data.fields.length)),rows=Math.max(...data.fields.map(f=>Math.ceil(data.innovations.filter(i=>i.field===f.id).length/3))),cellH=140+rows*70;W=cols*600;H=Math.ceil(data.fields.length/cols)*cellH;const centers=data.fields.map((f,n)=>[300+(n%cols)*600,cellH/2+Math.floor(n/cols)*cellH]);
 let rings='',nodes='';
 data.fields.forEach((f,fi)=>{
  let group=data.innovations.filter(i=>i.field===f.id),[cx,cy]=centers[fi];
  rings+=`<ellipse class="ring" cx="${cx}" cy="${cy}" rx="270" ry="${cellH/2-20}" stroke="${f.color}"/><text class="field-label" text-anchor="middle" x="${cx}" y="${cy-cellH/2+44}" fill="${f.color}" opacity="${field&&field!==f.id?.25:.85}">${esc(f.name.toUpperCase())}</text>`;
  group.forEach((i,n)=>{const x=cx-180+(n%3)*180,y=cy-cellH/2+90+Math.floor(n/3)*70;positions[i.id]={x,y};const active=shown.has(i.id);let label=wrap(i.title,23);if(label.length>3)label=[...label.slice(0,2),label[2]+'…'];
   nodes+=`<g class="node" role="button" tabindex="${active?0:-1}" aria-label="${esc(i.id+' '+i.title)}" data-id="${i.id}" opacity="${active?1:.12}" ${active?'':'aria-disabled="true"'}><circle class="halo" cx="${x}" cy="${y}" r="18" fill="${f.color}" opacity=".15"/><circle cx="${x}" cy="${y}" r="5" fill="${f.color}"/><text class="node-id" text-anchor="middle" x="${x}" y="${y-12}">${i.id}</text><text text-anchor="middle" x="${x}" y="${y+20}">${label.map((s,k)=>`<tspan x="${x}" dy="${k?13:0}">${esc(s)}</tspan>`).join('')}</text><title>${esc(i.title)}</title></g>`;
  });
 });
 $('#map').innerHTML=`<g id="map-camera">${rings}<g id="edges"></g>${nodes}</g>`;setView();
 $('#map').querySelectorAll('.node').forEach(n=>{
  if(!shown.has(n.dataset.id))return;
  n.onclick=()=>{if(!moved)openItem(n.dataset.id);};n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openItem(n.dataset.id);}};
  n.onmouseenter=n.onfocus=()=>showEdges(n.dataset.id,shown);n.onmouseleave=n.onblur=()=>$('#edges').innerHTML='';
 });
}
function showEdges(id,shown){$('#edges').innerHTML=data.connections.filter(e=>(e.source===id||e.target===id)&&shown.has(e.source)&&shown.has(e.target)).map(e=>{let a=positions[e.source],b=positions[e.target];return `<path class="edge" d="M${a.x},${a.y} Q${(a.x+b.x)/2},${Math.min(a.y,b.y)-120} ${b.x},${b.y}"/>`;}).join('');}
function setView(){const w=W/zoom,h=H/zoom;$('#map').setAttribute('viewBox',`${(W-w)/2+pan.x} ${(H-h)/2+pan.y} ${w} ${h}`);}
async function openItem(id,history=true){
 if(!data.innovations.some(i=>i.id===id))return;
 if($('#detail').hidden)focusReturn=document.activeElement;
 selected=id;let ticket=++request;$('#detail').hidden=false;$('#shade').hidden=false;document.body.style.overflow='hidden';$('#detail-content').innerHTML='<p>Loading reviewed record…</p>';$('#detail-label').textContent=id;$('#close').focus();
 if(history)window.history.replaceState(null,'','#'+id);
 try{
  const res=await fetch('/api/innovations/'+encodeURIComponent(id));if(!res.ok)throw new Error('Record unavailable');const i=await res.json();if(ticket!==request)return;
  const f=data.fields.find(f=>f.id===id.split('-')[0]);$('#detail-label').textContent=f.name+' / '+id;
  const sourceMap=new Map(i.sources.map((s,n)=>[s.url,n+1]));
  const cites=urls=>(urls||[]).length?`<div class="citations">${urls.map(u=>`<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer">${sourceMap.has(u)?'['+sourceMap.get(u)+'] ':''}Original source ↗</a>`).join('')}</div>`:'';
  const paragraphs=(ps,numbered)=>ps.map((p,n)=>`<p>${numbered?`<span class="milestone-no">MILESTONE ${n+1}</span> `:''}${esc(p.text)}</p>${cites(p.source_urls)}`).join('');
  $('#detail-content').innerHTML=`<div class="detail-kicker">PROPOSED BREAKTHROUGH / ${id}</div><h2 id="detail-title">${esc(i.title)}</h2><div class="detail-tags"><span>POST-REVIEW RECORD</span><span>${i.sources.length} SOURCES</span><span>01 NOV 2026</span></div><p class="lead">${esc(i.concept[0].text)}</p>${cites(i.concept[0].source_urls)}<nav class="section-nav" aria-label="Innovation sections">${sections.map(([k,v])=>`<a href="#section-${k}">${v}</a>`).join('')}<a href="#section-sources">Sources</a></nav>${sections.map(([k,v])=>`<section id="section-${k}"><h3>${v}</h3>${paragraphs(k==='concept'?i[k].slice(1):i[k],k==='completion_criteria')}${k==='concept'&&i[k].length===1?'<p class="small-note">The concept is described in the introduction above.</p>':''}${k==='related_concepts'?data.connections.filter(e=>e.source===id||e.target===id).map(e=>{const other=e.source===id?e.target:e.source;const item=data.innovations.find(x=>x.id===other);return `<button class="connection" data-related="${other}">${other} · ${esc(item.title)} ↗</button>`;}).join(''):''}</section>`).join('')}<details><summary>Evidence limitations · ${i.unresolved_issues.length}</summary><ul>${i.unresolved_issues.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details><section id="section-sources"><h3>Sources & saved copies</h3><p class="small-note">Original links open the publisher or repository. Saved copies download from this computer and may be partial. Capture is not proof of a claim.</p>${i.sources.map((s,n)=>`<div class="source"><div class="source-title">${n+1}. ${esc(s.title||new URL(s.url).hostname)}</div><div class="source-meta">${esc(s.status.replaceAll('_',' '))} · ${s.artifacts.length} saved ${s.artifacts.length===1?'file':'files'}</div><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">Original ↗</a>${s.artifacts.map(a=>`<a href="/api/assets/${a.sha256}">Download ${esc(a.format||'copy')}${a.kind==='abstract'?' (abstract)':''} ↓</a>`).join('')}</div>`).join('')}</section><details><summary>Review changes & provenance</summary><p class="small-note">Imported ${new Date(i.run.imported_at).toLocaleString()}. Original reviewed record retained without edits.</p><p class="small-note">Final record set SHA-256: <code>${i.run.hash}</code></p>${i.documents.map(k=>`<p><a href="/api/documents/${encodeURIComponent(id+':'+k)}">Download ${esc(k.replaceAll('_',' '))} ↓</a></p>`).join('')}<ul>${i.change_log.map(c=>`<li><strong>${esc(c.change)}</strong><br>${esc(c.reason)}</li>`).join('')}</ul></details>`;
  $('#detail').scrollTop=0;
  $('#detail-content').querySelectorAll('[data-related]').forEach(b=>b.onclick=()=>openItem(b.dataset.related));
  $('#detail-content').querySelectorAll('.section-nav a').forEach(a=>a.onclick=e=>{e.preventDefault();$('#detail-content').querySelector(a.getAttribute('href')).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});
 }catch(e){if(ticket===request)$('#detail-content').innerHTML=`<h2 id="detail-title">Unable to load this record</h2><p>${esc(e.message)}</p>`;}
}
function closeDetail(){request++;selected=null;$('#detail').hidden=true;$('#shade').hidden=true;document.body.style.overflow='';history.replaceState(null,'',location.pathname);focusReturn?.focus();}
function reset(){field=null;query='';$('#search').value='';zoom=1;pan={x:0,y:0};draw();}
$('#close').onclick=$('#shade').onclick=closeDetail;$('#clear').onclick=$('#empty-reset').onclick=reset;
$('#map-mode').onclick=()=>{mode='map';draw();};$('#list-mode').onclick=()=>{mode='list';draw();};$('#search').oninput=e=>{query=e.target.value.trim().toLowerCase();draw();};
$('#zoom-in').onclick=()=>{zoom=Math.min(8,zoom*1.25);setView();};$('#zoom-out').onclick=()=>{zoom=Math.max(.7,zoom/1.25);setView();};$('#zoom-reset').onclick=()=>{zoom=1;pan={x:0,y:0};setView();};
$('#map').addEventListener('pointerdown',e=>{moved=false;drag={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};});
window.addEventListener('pointermove',e=>{if(!drag)return;let dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>5){moved=true;const scale=W/$('#map').clientWidth/zoom;pan={x:drag.px-dx*scale,y:drag.py-dy*scale};setView();}});window.addEventListener('pointerup',()=>{drag=null;});
$('#about').onclick=()=>$('#about-dialog').showModal();$('#close-about').onclick=()=>$('#about-dialog').close();
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'&&!$('#detail').hidden){closeDetail();}
 if(e.key==='/'&&document.activeElement.tagName!=='INPUT'&&$('#detail').hidden){e.preventDefault();$('#search').focus();}
 if(e.key==='Tab'&&!$('#detail').hidden){const fs=[...$('#detail').querySelectorAll('button,a,summary')].filter(e=>e.getClientRects().length);const first=fs[0],last=fs.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
});
fetch('/api/catalog').then(r=>{if(!r.ok)throw Error('Database unavailable');return r.json();}).then(d=>{data=d;draw();let id=decodeURIComponent(location.hash.slice(1));if(id)openItem(id,false);}).catch(e=>{$('#result-count').textContent=e.message;$('#map-wrap').hidden=true;$('#empty').hidden=false;$('#empty').innerHTML='<h2>Collection unavailable</h2><p>Check that the local database has been imported, then reload.</p>';});

window.addEventListener('hashchange',()=>{if(!data)return;const id=decodeURIComponent(location.hash.slice(1));if(id&&data.innovations.some(i=>i.id===id))openItem(id,false);else if(!id&&!$('#detail').hidden)closeDetail();});
