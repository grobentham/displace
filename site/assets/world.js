'use strict';
/* Displace World pages. Every page is a view of site/data/world/*.json, written by engine/world.py.
   Text from data is always set with textContent, never as HTML. Saved items live only in this browser. */
(function(){
const KIND={market:'Market move',attention:'Coverage spike',filing:'Company filing',rule:'US rule',quake:'Earthquake',haze:'Singapore haze',release:'Economic release',trend:'Long-term base rate'};
const LABEL={hit:'Came true',miss:'Did not happen',unresolved:'Open',not_assessable:'Not assessable'};
const STORE='displace-world-v1';
const main=document.querySelector('main[data-page]');
const DATA=main?'../data/world/':null;

function el(tag,text,parent,cls){const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=text;if(cls)n.className=cls;if(parent)parent.append(n);return n}
function a(href,text,parent){const n=el('a',text,parent);n.href=href;return n}
function when(ts){try{return new Date(ts).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return ts}}
function pct(x){return x===null||x===undefined?'—':Math.round(x*100)+'%'}
function load(path){return fetch(DATA+path,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(path);return r.json()})}

/* device-only storage (works without an account; may be unavailable in private modes) */
function state(){try{return Object.assign({follow:[],saved:[],seen:null},JSON.parse(localStorage.getItem(STORE)||'{}'))}catch(e){return {follow:[],saved:[],seen:null}}}
function keep(s){try{localStorage.setItem(STORE,JSON.stringify(s));return true}catch(e){return false}}
function toggle(list,id){const s=state();const i=s[list].indexOf(id);if(i<0)s[list].push(id);else s[list].splice(i,1);keep(s);return i<0}

function saveButtons(root){
  for(const b of (root||document).querySelectorAll('[data-save]')){
    const id=b.dataset.save;b.setAttribute('aria-pressed',String(state().saved.includes(id)));
    b.textContent=state().saved.includes(id)?'Saved':'Save to My Displace';
    b.onclick=()=>{const on=toggle('saved',id);b.setAttribute('aria-pressed',String(on));b.textContent=on?'Saved':'Save to My Displace'}}}

function label(lab,parent){return el('span',LABEL[lab]||lab,parent,'wd-label wd-'+lab)}

function card(s,parent,prefix){
  const c=el('article',undefined,parent,'wd-card');
  const m=el('div',undefined,c,'wd-meta');el('span',KIND[s.kind]||s.kind,m,'wd-kind');el('span',(s.category||'').replace(/-/g,' '),m);el('span',when(s.published_at),m);
  if(s.horizon==='long')el('span','Long term',m);
  const h=el('h3',undefined,c);a((prefix||'')+'s/'+encodeURIComponent(s.id)+'.html',s.title,h);
  if(s.lead)el('p',s.lead,c);
  if(s.claims&&s.claims.length){const r=el('div',undefined,c,'wd-meta');el('span',s.claims.length+(s.claims.length>1?' claims':' claim'),r);for(const cl of s.claims)label(cl.label,r)}
  const b=el('button',undefined,c,'wd-save');b.type='button';b.dataset.save=s.id;saveButtons(c);return c}

function list(rows,root,prefix,step){
  let shown=0;step=step||25;const box=el('div',undefined,root,'wd-cards');const more=el('button','Show more',root,'wd-btn wd-more');
  function next(){for(const s of rows.slice(shown,shown+step))card(s,box,prefix);shown+=step;more.hidden=shown>=rows.length}
  more.onclick=next;next();if(!rows.length)el('p','Nothing here yet. The engine adds signals every three hours.',box,'wd-empty');return box}

function status(text){const n=main.querySelector('#status');if(n)n.textContent=text}

const PAGES={
signals(){
  return load('feed.json').then(d=>{
    const f=el('div',undefined,main,'wd-filters');
    const cat=el('select',undefined,f);cat.setAttribute('aria-label','Category');el('option','All categories',cat).value='';
    const kind=el('select',undefined,f);kind.setAttribute('aria-label','Kind');el('option','All kinds',kind).value='';
    for(const k of Object.keys(KIND)){const o=el('option',KIND[k],kind);o.value=k}
    const cats=[...new Set(d.signals.map(s=>s.category))].sort();for(const c of cats){const o=el('option',c.replace(/-/g,' '),cat);o.value=c}
    const q=el('input',undefined,f);q.type='search';q.placeholder='Search company, topic, country';q.setAttribute('aria-label','Search signals');
    const p=new URLSearchParams(location.search);cat.value=p.get('category')||'';kind.value=p.get('kind')||'';
    const out=el('div',undefined,main);
    function draw(){out.textContent='';const w=q.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      const rows=d.signals.filter(s=>(!cat.value||s.category===cat.value)&&(!kind.value||s.kind===kind.value)&&w.every(x=>(s.title+' '+s.lead+' '+(s.entities.companies||[]).join(' ')).toLowerCase().includes(x)));
      status(rows.length+' of '+d.count+' signals · updated '+when(d.generated));list(rows,out,'')}
    for(const x of [cat,kind])x.onchange=draw;q.oninput=draw;draw()})},
early(){
  return load('early/index.json').then(d=>{
    if(!d.editions.length){status('The first Early edition is published after 06:00 Singapore time.');return}
    status(d.editions.length+' editions');const latest=d.editions[0];
    return load('early/'+latest.date+'.json').then(ed=>{
      const s=el('section',undefined,main,'panel');el('p','Latest edition · '+ed.date,s,'wd-kicker');const h=el('h2',undefined,s);a('early/'+ed.date+'.html',ed.title,h);
      el('p',ed.signal_count+' new signals in the 24 hours to '+when(ed.coverage_to)+'.',s,'muted');
      for(const sec of ed.sections){el('h3',sec.title,s);const ul=el('ul',undefined,s,'wd-list');for(const x of sec.signals){const li=el('li',undefined,ul);a('s/'+encodeURIComponent(x.id)+'.html',x.title,li)}}
      const arch=el('section',undefined,main,'panel');el('h2','Earlier editions',arch);const ul=el('ul',undefined,arch,'wd-list');
      for(const e of d.editions){const li=el('li',undefined,ul);a('early/'+e.date+'.html',e.date+' · '+e.title,li)}})})},
connections(){
  return load('connections/index.json').then(ix=>{
    if(!ix.days.length){status('No connection maps yet.');return}
    const pick=el('select',undefined,el('div',undefined,main,'wd-filters'));pick.setAttribute('aria-label','Day');for(const d of ix.days){const o=el('option',d,pick);o.value=d}
    const out=el('div',undefined,main);
    function draw(){load('connections/'+pick.value+'.json').then(c=>{out.textContent='';const by={};for(const n of c.nodes)by[n.id]=n;
      status(c.routes.length+' routes from '+c.signals_considered+' signals of the 72 hours to '+c.date);
      if(!c.routes.length)el('p','No two signals in different categories were linked on this day.',out,'wd-empty');
      for(const r of c.routes){const box=el('section',undefined,out,'wd-route');
        el('p',(r.degrees===0?'Direct link':r.degrees+(r.degrees===1?' story':' stories')+' in between')+' · '+r.documented+' of '+r.links.length+(r.links.length===1?' link':' links')+' documented',box,'wd-kicker');
        box.append(svg(r,by));const ol=el('ol',undefined,box,'wd-chain');
        r.path.forEach((id,i)=>{const li=el('li',undefined,ol);a('s/'+encodeURIComponent(id)+'.html',by[id].title,li);
          if(i<r.links.length){const e=el('div',({documented:'Documented: ',topic:'Related topics: ','co-mentioned':'Same country: '}[r.links[i].type]||'')+r.links[i].basis,ol,'wd-edge'+(r.links[i].type==='documented'?'':' co'))}})}
      el('p','A link shows that two signals share a documented relation or a name. It does not show that one caused the other.',out,'muted')})}
    pick.onchange=draw;draw()})},
'long-term'(){return load('long-term.json').then(d=>{status(d.signals.length+' long-term signals');list(d.signals,main,'')})},
'before-the-headlines'(){
  return load('before-the-headlines.json').then(d=>{status(d.entries.length+' timing comparisons');
    if(!d.entries.length)el('p','No comparisons yet. Displace records one when a major outlet reports the same thing after a World signal.',main,'wd-empty');
    for(const t of d.entries){const s=el('section',undefined,main,'panel');const h=el('h3',undefined,s);a('s/'+encodeURIComponent(t.signal_id)+'.html',t.signal_title,h);
      const ol=el('ol',undefined,s);el('li','Displace signal: '+when(t.signal_published),ol);const li=el('li','Later report ('+t.later_publisher+', first seen '+when(t.later_seen)+'): ',ol);a(t.later_url,t.later_title,li);
      const m=t.delay_minutes,txt=m<90?m+' minutes':m<2880?Math.round(m/60)+' hours':Math.round(m/1440)+' days';
      el('p','Published about '+txt+' earlier. '+t.qualification+' A later report does not prove the outcome, worldwide priority or influence.',s,'muted')}})},
'came-true'(){
  return load('came-true.json').then(d=>{status(d.count+' claims came true. Misses are on the Trust page.');
    for(const c of d.cases){const s=el('section',undefined,main,'panel');const h=el('h3',undefined,s);a('s/'+encodeURIComponent(c.signal)+'.html',c.signal_title,h);
      const ol=el('ol',undefined,s);el('li','What Displace said ('+when(c.frozen_at)+'): '+c.predicted+(c.probability!=null?' ('+pct(c.probability)+' historically)':''),ol);el('li','What happened ('+when(c.assessed_at)+'): '+c.happened,ol);label(c.label,s)}})},
learns(){
  return load('learns.json').then(d=>{
    const p=el('section',undefined,main,'panel');el('h2','What Displace has learned',p);const ul=el('ul',undefined,p,'wd-list');
    for(const l of d.lessons){el('li',l.text,ul)}if(!d.lessons.length)el('li','No claims graded yet.',ul,'wd-empty');
    const q=el('section',undefined,main,'panel');el('h2','Research principles',q);const ol=el('ol',undefined,q);
    for(const x of d.principles){const li=el('li',undefined,ol);el('strong',x.principle,li);el('div',x.practice,li,'muted')}
    const c=el('section',undefined,main,'panel');el('h2','Graded claims',c);const f=el('select',undefined,el('div',undefined,c,'wd-filters'));f.setAttribute('aria-label','Outcome');
    for(const [v,t] of [['','All outcomes'],['hit','Came true'],['miss','Did not happen'],['not_assessable','Not assessable']]){const o=el('option',t,f);o.value=v}
    const box=el('div',undefined,c);function draw(){box.textContent='';for(const x of d.cases.filter(x=>!f.value||x.label===f.value)){const s=el('div',undefined,box,'wd-route');label(x.label,s);
      const h=el('p',undefined,s);a('s/'+encodeURIComponent(x.signal)+'.html',x.signal_title,h);
      for(const [k,v] of [['What we predicted',x.predicted],['What actually happened',x.happened],['What we learned',x.learned],['What remains uncertain',x.open||'Nothing: graded by rule.'],['What we will check next',x.next]]){const r=el('p',undefined,s);el('strong',k+': ',r);r.append(v||'—')}}}
    f.onchange=draw;draw();status(d.cases.length+' graded claims')})},
trust(){
  return load('trust.json').then(d=>{const sc=d.scorecard;const t=el('div',undefined,main,'wd-tiles');
    for(const [v,k] of [[sc.signals,'Signals published'],[sc.claims,'Claims frozen'],[sc.labels.hit,'Came true'],[sc.labels.miss,'Did not happen'],[sc.labels.unresolved,'Open'],[sc.labels.not_assessable,'Not assessable'],[pct(sc.hit_rate),'Hit rate of graded'],[sc.brier===null?'—':sc.brier,'Brier score (coin = 0.25)'],[sc.corrections,'Corrections']]){const x=el('div',undefined,t,'wd-tile');el('b',v,x);el('span',k,x)}
    const cal=el('section',undefined,main,'panel');el('h2','Calibration',cal);el('p','For claims that carried a historical probability: when Displace said about X%, how often did it happen?',cal,'muted');
    const tb=el('table',undefined,el('div',undefined,cal,'scroll'),'wd-claims');const hr=el('tr',undefined,el('thead',undefined,tb));for(const h of ['Stated probability','Claims','Average stated','Came true'])el('th',h,hr);
    const body=el('tbody',undefined,tb);for(const b of sc.calibration){const r=el('tr',undefined,body);for(const v of [b.range,b.n,pct(b.average_probability),pct(b.came_true)])el('td',v,r)}
    const br=el('section',undefined,main,'panel');el('h2','By rule',br);const t2=el('table',undefined,el('div',undefined,br,'scroll'),'wd-claims');const h2=el('tr',undefined,el('thead',undefined,t2));for(const h of ['Rule','Came true','Did not happen','Open','Not assessable'])el('th',h,h2);
    const b2=el('tbody',undefined,t2);for(const [k,v] of Object.entries(sc.by_rule)){const r=el('tr',undefined,b2);for(const x of [(sc.rule_names||{})[k]||k.replace(/_/g,' '),v.hit||0,v.miss||0,v.unresolved||0,v.not_assessable||0])el('td',x,r)}
    const w=el('section',undefined,main,'panel');el('h2','What we got wrong',w);const wl=el('ul',undefined,w,'wd-list');if(!d.misses.length)el('li','No misses yet.',wl,'wd-empty');
    for(const m of d.misses){const li=el('li',undefined,wl);a('s/'+encodeURIComponent(m.signal)+'.html',m.predicted,li);el('div',m.happened+(m.probability!=null?' (stated '+pct(m.probability)+')':''),li,'muted')}
    const co=el('section',undefined,main,'panel');el('h2','Corrections',co);el('p','Report an error with the signal link, the exact passage and a dated source. Corrections keep the original wording and the reason.',co,'muted');
    const cl=el('ul',undefined,co,'wd-list');if(!d.corrections.length)el('li','No corrections published.',cl,'wd-empty');for(const c of d.corrections){el('li',c.date+' · '+c.target+' · '+c.reason+(c.label?' · label now '+(LABEL[c.label]||c.label):''),cl)}
    const ch=el('section',undefined,main,'panel');el('h2','Change history',ch);const hl=el('ul',undefined,ch,'wd-list');for(const c of d.changes.slice(0,60)){el('li',when(c.at)+' · '+c.claim+' → '+(LABEL[c.label]||c.label)+' · '+c.note,hl)}
    const src=el('section',undefined,main,'panel');el('h2','Source health',src);const sl=el('ul',undefined,src,'wd-list');const hs=(d.health&&d.health.sources)||{};
    const groups={};for(const [k,v] of Object.entries(hs)){const g=k.split(':')[0];groups[g]=groups[g]||{ok:0,bad:0};groups[g][v.ok?'ok':'bad']++}
    for(const [g,v] of Object.entries(groups))el('li',g+': '+v.ok+' requests answered, '+v.bad+' failed (last run '+when(d.health.checked_at)+')',sl);if(!Object.keys(groups).length)el('li','No network run recorded yet.',sl,'wd-empty');
    const ind=el('section',undefined,main,'panel');el('h2','Research independence and integrity',ind);
    el('p','Displace takes no payment, sponsorship or advertising for coverage. Signals are produced by fixed rules in a public repository; no person chooses which events appear and no AI model writes them.',ind);
    const ip=el('p','Every claim is stored with a SHA-256 hash ('+d.integrity.claims_hashed+' so far) and the engine refuses to change a stored claim. The public commit history is the timestamp record: ',ind);a(d.integrity.history,'ledger history on GitHub',ip);
    status('Updated '+when(d.generated))})},
topics(){
  return Promise.all([load('topics.json'),load('feed.json')]).then(([t,f])=>{const id=new URLSearchParams(location.search).get('c');
    const c=t.categories.find(x=>x.id===id);
    if(!c){status(t.categories.length+' categories · '+t.categories.reduce((n,x)=>n+x.areas.length,0)+' research areas');
      const g=el('div',undefined,main,'wd-grid');for(const x of t.categories){const k=el('div',undefined,g,'wd-card');const h=el('h3',undefined,k);a('?c='+x.id,x.name,h);el('p',x.description,k);el('p',x.count+' signals · '+x.areas.length+' areas',k,'muted');followBtn(x.id,k)}return}
    document.title=c.name+' | Displace World';el('h2',c.name,main);el('p',c.description,main);
    const r=el('div',undefined,main,'wd-filters');followBtn(c.id,r);a('feeds/'+c.id+'.xml','RSS feed',r);a('index.html?category='+c.id,'All '+c.name.toLowerCase()+' signals',r);
    const ar=el('section',undefined,main,'panel');el('h3','Research areas',ar);const ul=el('ul',undefined,ar);for(const x of c.areas)el('li',x.name+' · '+x.count+' signals',ul);
    status(c.count+' signals');list(f.signals.filter(s=>s.category===c.id),main,'')})},
radar(){
  return Promise.all([load('feed.json'),load('topics.json')]).then(([f,t])=>{const s=state();const last=s.seen;s.seen=new Date().toISOString();const ok=keep(s);
    if(!ok)el('p','This browser is not letting Displace store your choices (private mode or blocked storage). Follows and saves will reset when you leave.',main,'wd-empty');
    const fl=el('section',undefined,main,'panel');el('h2','Topics you follow',fl);el('p','Stored only in this browser. No account, no tracking.',fl,'muted');
    const g=el('div',undefined,fl,'wd-filters');for(const c of t.categories)followBtn(c.id,g,c.name,()=>draw());
    const io=el('div',undefined,fl,'wd-filters');const ex=el('button','Copy my settings',io,'wd-btn');const im=el('button','Paste settings from another device',io,'wd-btn');
    ex.onclick=()=>{const txt=JSON.stringify({follow:state().follow,saved:state().saved});navigator.clipboard&&navigator.clipboard.writeText(txt).then(()=>{ex.textContent='Copied'},()=>{prompt('Copy this text:',txt)})};
    im.onclick=()=>{const txt=prompt('Paste the settings text from your other device:');if(!txt)return;try{const v=JSON.parse(txt);const st=state();st.follow=[...new Set([...(st.follow||[]),...(v.follow||[])])];st.saved=[...new Set([...(st.saved||[]),...(v.saved||[])])];keep(st);location.reload()}catch(e){alert('That text is not valid settings.')}};
    const out=el('div',undefined,main);
    function draw(){out.textContent='';const st=state();
      const sv=el('section',undefined,out,'panel');el('h2','Saved signals',sv);const saved=f.signals.filter(x=>st.saved.includes(x.id));if(!saved.length)el('p','Save a signal with the “Save to My Displace” button.',sv,'wd-empty');else list(saved,sv,'',10);
      const rd=el('section',undefined,out,'panel');el('h2','Your radar',rd);
      if(!st.follow.length){el('p','Follow a few topics above to build your radar.',rd,'wd-empty');return}
      const rows=f.signals.filter(x=>st.follow.includes(x.category));const fresh=last?rows.filter(x=>x.published_at>last):[];
      el('p',(last?fresh.length+' new since your last visit ('+when(last)+') · ':'')+rows.length+' signals in your topics',rd,'muted');
      for(const id of st.follow)a('feeds/'+id+'.xml','RSS: '+id.replace(/-/g,' '),el('span',' ',rd));
      list(rows,rd,'',20)}
    draw();status('Updated '+when(f.generated))})},
business(){
  const form=main.querySelector('#brief');if(!form)return Promise.resolve();
  form.onsubmit=e=>{e.preventDefault();const v=k=>form.elements[k].value.trim();
    const body='Sector: '+v('sector')+'\nMarket or country: '+v('market')+'\nDecision to make: '+v('decision')+'\nTime horizon: '+v('horizon')+'\n\nPlease use only public or non-sensitive information.';
    location.href='https://github.com/grobentham/displace/issues/new?labels=research-request&title='+encodeURIComponent('Research request: '+v('decision').slice(0,80))+'&body='+encodeURIComponent(body)};
  return Promise.resolve()}
};

function followBtn(id,parent,name,after){const b=el('button',undefined,parent,'wd-btn');b.type='button';
  const set=()=>{const on=state().follow.includes(id);b.setAttribute('aria-pressed',String(on));b.textContent=(on?'Following ':'Follow ')+(name||'this topic')};
  set();b.onclick=()=>{toggle('follow',id);set();if(after)after()};return b}

function svg(r,by){ /* a left-to-right map of one route: solid = documented, dashed = co-mentioned */
  const NS='http://www.w3.org/2000/svg',n=r.path.length,w=760,h=120,gap=(w-80)/Math.max(1,n-1);
  const s=document.createElementNS(NS,'svg');s.setAttribute('viewBox','0 0 '+w+' '+h);s.setAttribute('class','wd-svg');s.setAttribute('role','img');s.setAttribute('aria-label','Route map with '+n+' signals');
  const x=i=>n===1?w/2:40+i*gap;
  r.links.forEach((l,i)=>{const p=document.createElementNS(NS,'line');p.setAttribute('x1',x(i));p.setAttribute('x2',x(i+1));p.setAttribute('y1',50);p.setAttribute('y2',50);p.setAttribute('stroke',l.type==='documented'?'#0071e3':'#b25000');p.setAttribute('stroke-width','2');if(l.type!=='documented')p.setAttribute('stroke-dasharray','6 5');s.append(p)});
  r.path.forEach((id,i)=>{const c=document.createElementNS(NS,'circle');c.setAttribute('cx',x(i));c.setAttribute('cy',50);c.setAttribute('r',9);c.setAttribute('fill','#fff');c.setAttribute('stroke','#1d1d1f');c.setAttribute('stroke-width','1.5');s.append(c);
    const t=document.createElementNS(NS,'text');t.setAttribute('x',x(i));t.setAttribute('y',86);t.setAttribute('text-anchor',n>1&&i===0?'start':n>1&&i===n-1?'end':'middle');if(n>1&&i===0)t.setAttribute('x',x(i)-9);if(n>1&&i===n-1)t.setAttribute('x',x(i)+9);t.setAttribute('font-size','12');t.setAttribute('fill','#1d1d1f');t.textContent=(KIND[by[id].kind]||'')+': '+by[id].category.replace(/-/g,' ');s.append(t)});
  return s}

saveButtons();
if(main){const fn=PAGES[main.dataset.page];if(fn)fn().catch(()=>status('This section has not been published yet or is temporarily unavailable.'))}
if(typeof module!=='undefined')module.exports={KIND,LABEL};
})();
