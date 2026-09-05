(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('archive-data').textContent);
  const $ = id => document.getElementById(id);
  const canvas = $('graph'), ctx = canvas.getContext('2d');
  const colors = {knowledge:'#347e79',event:'#ba6743',node:'#6887ad',collection:'#9173a2',source:'#9c927f'};
  const types = {knowledge:'知识档案',event:'事件',node:'目录对象',collection:'专题集合',source:'来源'};
  const words={fact:'事实论断',allegation:'待核实说法',memory:'回忆',interpretation:'解释',high:'把握较高',medium:'把握一般',low:'把握较低',unknown:'未知',current:'当前有效',superseded:'已被替代',supports:'支持证据',contradicts:'反证',context:'上下文',day:'精确到日',month:'精确到月',year:'精确到年',exact:'明确',approximate:'大致',uncertain:'不确定'};
  const word=value=>words[value]||value;
  const nodes = new Map(data.nodes.map(n => [n.id,{...n}]));
  const adjacency = new Map(data.nodes.map(n => [n.id,new Set()]));
  for (const e of data.edges) { adjacency.get(e.from).add(e.to); adjacency.get(e.to).add(e.from); }
  let width=0,height=0,dpr=1,camera={x:0,y:0,scale:1}, selected=null,focused=false,expanded=new Set(),shown=[],edges=[],filterTypes=new Set(Object.keys(types).filter(t=>t!=='source'));
  let scheduled=false, hover=null, searchPage=100;
  const safeURL = value => { try {const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password ? u.href:null;}catch{return null;} };
  function element(tag,text,container,cls) {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;if(container)container.append(e);return e;}
  function recordButton(id,container,prefix='') {const n=nodes.get(id);if(!n)return;const b=element('button',prefix+n.label,container,'record-link');b.addEventListener('click',()=>select(id));return b;}
  function externalLink(url,title,container) {const href=safeURL(url);if(!href)return;const a=element('a',title,container);a.href=href;a.target='_blank';a.rel='noopener noreferrer';}
  function prose(text,container) {
    // Text nodes only. Markdown navigation is recognized without injecting source HTML.
    const pattern=/\[\[([a-z0-9-]+)(?:\|([^\]]+))?\]\]|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
    for(const paragraph of String(text||'').split(/\n\s*\n/)) {
      const heading=/^#{1,6}\s+([^\n]+)$/.exec(paragraph);if(heading){element('h3',heading[1],container);continue;}
      const p=element('p',undefined,container);let last=0;
      for(const match of paragraph.matchAll(pattern)){p.append(document.createTextNode(paragraph.slice(last,match.index)));if(match[1]&&nodes.has(match[1])){const b=element('button',match[2]||nodes.get(match[1]).label,p);b.addEventListener('click',()=>select(match[1]));}else if(match[4])externalLink(match[4],match[3],p);else p.append(document.createTextNode(match[0]));last=match.index+match[0].length;}
      p.append(document.createTextNode(paragraph.slice(last)));
    }
  }
  function details(id) {
    const item=data.details[id], panel=$('detail-body');panel.replaceChildren();$('detail-type').textContent=types[nodes.get(id).type];
    element('h2',nodes.get(id).label,panel);prose(item.summary,panel);
    if(item.time){element('h3','事件时间',panel);element('p',`${item.time.start||'未知'}${item.time.end?' — '+item.time.end:''} · ${word(item.time.precision)} · ${word(item.time.certainty)}`,panel);}
    if(item.validity){element('h3','有效期与核验',panel);element('p',`${item.validity.start||'未知'} — ${item.validity.end||'未知'}\n状态：${word(item.validity.state)} · 核验：${item.validity.verified_at||'未知'}`,panel);}
    if(item.body){const body=element('section',undefined,panel,'body-text');prose(item.body,body);}
    for(const claim of item.claims||[]){const c=element('div',undefined,panel,'claim');element('small',`${word(claim.kind)} · ${word(claim.certainty||'unknown')}`,c);prose(claim.text,c);for(const cite of claim.citations){recordButton(cite.source_id,c,`${word(cite.role)} · `);element('small',cite.locator||'来源整体',c);if(cite.note)element('small',cite.note,c);}}
    if(item.locator){element('h3','来源定位',panel);for(const key of ['original_url','archive_url'])if(item.locator[key]){const p=element('p',undefined,panel);externalLink(item.locator[key],key==='original_url'?'打开原始来源 ↗':'打开存档来源 ↗',p);}if(item.dates?.accessed_at)element('small','读取时间：'+item.dates.accessed_at,panel);}
    const related=[...adjacency.get(id)].filter(rid=>nodes.get(rid).type!=='source');
    if(related.length){element('h3',`相关档案 · ${related.length}`,panel);for(const rid of related)recordButton(rid,panel);}
    const sources=[...adjacency.get(id)].filter(rid=>nodes.get(rid).type==='source');
    if(sources.length){element('h3',`来源 · ${sources.length}`,panel);for(const rid of sources)recordButton(rid,panel);}
    element('h3','档案标识',panel);element('small',id,panel);element('small','真源：'+item.canonical_path,panel);
    $('detail').hidden=false;panel.scrollTop=0;
  }
  function select(id) {if(!nodes.has(id))return;selected=id;filterTypes.add(nodes.get(id).type);const checkbox=document.querySelector(`[data-type="${nodes.get(id).type}"]`);if(checkbox)checkbox.checked=true;expanded=new Set([id,...adjacency.get(id)]);if(nodes.get(id).type==='source'){$('sources').checked=true;filterTypes.add('source');}details(id);$('focus').disabled=false;$('results').hidden=true;location.hash=encodeURIComponent(id);refresh();}
  function refresh(){
    shown=[...nodes.values()].filter(n=>filterTypes.has(n.type)&&(!focused||expanded.has(n.id)));
    const visible=new Set(shown.map(n=>n.id));edges=data.edges.filter(e=>visible.has(e.from)&&visible.has(e.to)&&($('navigation').checked||e.kind!=='navigation'));
    $('empty').hidden=shown.length>0;$('all').classList.toggle('active',!focused);$('focus').classList.toggle('active',focused);
    $('status').textContent=`${shown.length} / ${nodes.size} 个公开节点 · ${edges.length} 条关系${focused?' · 局部图':''}`;
    requestDraw();
  }
  function world(x,y){return{x:(x-width/2-camera.x)/camera.scale,y:(y-height/2-camera.y)/camera.scale};}
  function screen(n){return{x:n.x*camera.scale+width/2+camera.x,y:n.y*camera.scale+height/2+camera.y};}
  function requestDraw(){if(!scheduled){scheduled=true;requestAnimationFrame(draw);}}
  function draw(){scheduled=false;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
    ctx.lineWidth=.7;const near=selected?adjacency.get(selected):new Set();
    for(const e of edges){const a=screen(nodes.get(e.from)),b=screen(nodes.get(e.to));const relevant=e.from===selected||e.to===selected;ctx.strokeStyle=relevant?'#729b87':selected?'#dfe5db':'#c5d1c2';ctx.lineWidth=relevant?1.3:.7;ctx.setLineDash(e.kind==='navigation'?[3,5]:[]);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
    ctx.setLineDash([]);ctx.textBaseline='middle';ctx.font='11px system-ui, sans-serif';
    const labelCandidates=[];
    for(const n of shown){const p=screen(n);if(p.x<-180||p.x>width+100||p.y<-30||p.y>height+30)continue;const active=n.id===selected||n.id===hover;const radius=active?7:n.type==='source'?3:4.5;ctx.globalAlpha=selected&&!active&&!near.has(n.id)?.42:1;if(active){ctx.beginPath();ctx.arc(p.x,p.y,12,0,Math.PI*2);ctx.fillStyle='#e3eadb';ctx.fill();}ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);ctx.fillStyle=colors[n.type];ctx.fill();if(active||near.has(n.id)||shown.length<=70||camera.scale>1.8)labelCandidates.push({n,p,active,priority:active?0:near.has(n.id)?1:2});}
    ctx.globalAlpha=1;
    const occupied=[];
    labelCandidates.sort((a,b)=>a.priority-b.priority||a.n.id.localeCompare(b.n.id));
    for(const {n,p,active,priority} of labelCandidates.slice(0,250)){
      const title=n.label.length>32?n.label.slice(0,31)+'…':n.label,w=ctx.measureText(title).width;
      const candidates=[[p.x+11,p.y-7],[p.x-w-11,p.y-7],[p.x-w/2,p.y+12],[p.x-w/2,p.y-25]];
      for(const [x,y] of candidates){const box={x,y,w:w+5,h:16};if(x<12||x+w>width-12||y<115&&width<580||y<85||y>height-100)continue;if(occupied.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y))continue;occupied.push(box);ctx.globalAlpha=selected&&priority===2?.5:1;ctx.fillStyle=active?'#193c32':'#3c5145';ctx.fillText(title,x,y+7);break;}
    }
    ctx.globalAlpha=1;
  }
  function fit(){if(!shown.length){camera={x:0,y:0,scale:1};requestDraw();return;}const xs=shown.map(n=>n.x),ys=shown.map(n=>n.y),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);const usableWidth=Math.max(240,width-180),usableHeight=Math.max(170,height-(width<580?250:210));camera.scale=Math.max(.04,Math.min(3.6,usableWidth/Math.max(maxx-minx,100),usableHeight/Math.max(maxy-miny,100)));camera.x=-(minx+maxx)/2*camera.scale;camera.y=-(miny+maxy)/2*camera.scale+(width<580?25:0);requestDraw();}
  function zoom(factor,x=width/2,y=height/2){const at=world(x,y);camera.scale=Math.max(.025,Math.min(12,camera.scale*factor));camera.x=x-width/2-at.x*camera.scale;camera.y=y-height/2-at.y*camera.scale;requestDraw();}
  const pointers=new Map();let drag=null,pinch=null;
  function hit(x,y){let best=null,distance=13;for(const n of shown){const p=screen(n),d=Math.hypot(p.x-x,p.y-y);if(d<distance){best=n;distance=d;}}return best;}
  canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(pointers.size===1)drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,node:hit(e.clientX,e.clientY),moved:false};else{drag=null;const p=[...pointers.values()];pinch=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);}});
  canvas.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId)){hover=hit(e.clientX,e.clientY)?.id||null;requestDraw();return;}pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(pointers.size===2){const p=[...pointers.values()],distance=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);if(pinch>0)zoom(distance/pinch,(p[0].x+p[1].x)/2,(p[0].y+p[1].y)/2);pinch=distance;return;}if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)>4)drag.moved=true;if(drag.moved){if(drag.node){drag.node.x+=dx/camera.scale;drag.node.y+=dy/camera.scale;}else{camera.x+=dx;camera.y+=dy;}}drag.x=e.clientX;drag.y=e.clientY;requestDraw();}});
  const endPointer=e=>{if(drag&&!drag.moved&&drag.node)select(drag.node.id);pointers.delete(e.pointerId);drag=null;pinch=null;};
  canvas.addEventListener('pointerup',endPointer);canvas.addEventListener('pointercancel',e=>{pointers.delete(e.pointerId);drag=null;pinch=null;});
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-e.deltaY*.0015),e.clientX,e.clientY);},{passive:false});
  function results(){const q=$('search').value.trim().toLocaleLowerCase();const matches=[...nodes.values()].filter(n=>[n.label,n.id,data.details[n.id].summary||''].some(t=>t.toLocaleLowerCase().includes(q)));const list=$('results');list.replaceChildren();list.hidden=false;for(const n of matches.slice(0,searchPage)){const b=element('button',n.label,list);element('small',types[n.type]+' · '+n.id,b);b.addEventListener('click',()=>{select(n.id);const p=nodes.get(n.id);camera.x=-p.x*camera.scale;camera.y=-p.y*camera.scale;requestDraw();});}if(!matches.length)element('p','没有找到相符的公开档案。',list);if(matches.length>searchPage){const b=element('button',`继续显示（共 ${matches.length} 条）`,list);b.addEventListener('click',()=>{searchPage+=100;results();});}}
  $('search').addEventListener('input',()=>{searchPage=100;results();});$('search').addEventListener('keydown',e=>{if(e.key==='ArrowDown'){$('results').querySelector('button')?.focus();e.preventDefault();}if(e.key==='Enter')$('results').querySelector('button')?.click();});$('results').addEventListener('keydown',e=>{if(e.key==='ArrowDown')e.target.nextElementSibling?.focus();if(e.key==='ArrowUp')e.target.previousElementSibling?.focus();});$('list-toggle').onclick=()=>{$('results').hidden?results():$('results').hidden=true;};
  for(const [type,title] of Object.entries(types)){if(type==='source')continue;const l=element('label',undefined,$('type-filters'));const input=element('input',undefined,l);input.type='checkbox';input.checked=true;input.dataset.type=type;l.append(document.createTextNode(title));input.onchange=()=>{input.checked?filterTypes.add(type):filterTypes.delete(type);refresh();};}
  $('sources').onchange=()=>{$('sources').checked?filterTypes.add('source'):filterTypes.delete('source');refresh();};$('navigation').onchange=refresh;
  for(const panel of ['filters','help']){const button=$(panel==='filters'?'filter-toggle':'help-toggle');button.onclick=()=>{$(panel).hidden=!$(panel).hidden;button.setAttribute('aria-expanded',String(!$(panel).hidden));};}
  $('close-detail').onclick=()=>{$('detail').hidden=true;};$('all').onclick=()=>{focused=false;refresh();fit();};
  $('focus').onclick=$('focus-detail').onclick=()=>{if(selected){focused=true;refresh();fit();}};
  $('expand').onclick=()=>{if(!selected)return;focused=true;for(const id of [...expanded])for(const target of adjacency.get(id))expanded.add(target);refresh();fit();};
  $('zoom-in').onclick=()=>zoom(1.3);$('zoom-out').onclick=()=>zoom(1/1.3);$('reset').onclick=()=>{for(const original of data.nodes)Object.assign(nodes.get(original.id),original);fit();};
  $('clear-filters').onclick=()=>{filterTypes=new Set(Object.keys(types).filter(t=>t!=='source'));for(const i of $('type-filters').querySelectorAll('input'))i.checked=true;$('sources').checked=false;$('navigation').checked=true;focused=false;refresh();fit();};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){for(const id of ['detail','filters','help','results'])$(id).hidden=true;$('filter-toggle').setAttribute('aria-expanded','false');$('help-toggle').setAttribute('aria-expanded','false');}if(e.target instanceof HTMLInputElement)return;if(e.key==='+'||e.key==='=')zoom(1.3);if(e.key==='-')zoom(1/1.3);if(e.key==='0')fit();});
  $('revision').textContent='公开内容版本：'+data.dataset_revision;
  function resize(){width=canvas.clientWidth;height=canvas.clientHeight;dpr=Math.min(devicePixelRatio||1,3);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);requestDraw();}
  new ResizeObserver(resize).observe(canvas);resize();refresh();fit();
  let initial='';try{initial=decodeURIComponent(location.hash.slice(1));}catch{}if(nodes.has(initial))select(initial);
})();
