'use strict';
/* ES / NQ divergence page: a view of data/smt/current.json (engine/smt.py). Text is set with textContent only. */
(function(){
const $=id=>document.getElementById(id);
let doc=null,tf='5m';
function el(tag,text,parent,cls){const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=text;if(cls)n.className=cls;if(parent)parent.append(n);return n}
function ny(ts){try{return new Date(ts).toLocaleString('en-US',{timeZone:'America/New_York',weekday:'short',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})+' NY'}catch(e){return ts}}
function pct(x){return x===null||x===undefined?'—':Math.round(x*100)+'%'}
function num(x){return x===null||x===undefined?'—':Number(x).toLocaleString('en-US',{maximumFractionDigits:2})}
function table(t,head,rows){t.textContent='';const tr=el('tr',undefined,el('thead',undefined,t));for(const h of head)el('th',h,tr);const b=el('tbody',undefined,t);for(const r of rows){const x=el('tr',undefined,b);for(const c of r){const td=el('td',undefined,x);if(c instanceof Node)td.append(c);else td.textContent=c}}if(!rows.length){const x=el('tr',undefined,b);const td=el('td','Nothing yet.',x,'muted');td.colSpan=head.length}}
function tag(text,cls){return el('span',text,null,'tag '+cls)}
function describe(e){return (e.direction==='bearish'?'Bearish':'Bullish')+' at '+e.level+': '+e.leader+' made it, '+e.laggard+' did not'}
function draw(){
  const d=doc.timeframes[tf];
  for(const b of document.querySelectorAll('#tf button'))b.setAttribute('aria-pressed',String(b.dataset.v===tf));
  if(!d){$('status').textContent='Not enough ES and NQ bars for this timeframe yet.';return}
  $('status').textContent='Updated '+ny(doc.asof)+' · '+d.bars.toLocaleString()+' bars from '+ny(d.from)+' · '+d.count+' divergences recorded';
  $('headline').textContent=d.today.length?d.today.length+(d.today.length>1?' divergences':' divergence')+' this session. Latest: '+describe(d.today[d.today.length-1])+' ('+ny(d.today[d.today.length-1].confirmed_at)+').':'No divergence confirmed this session so far.';
  table($('board'),['Level','NQ level','NQ','ES level','ES','State'],d.levels.map(l=>{const st=!l.active?tag('Not set yet','quiet'):l.nq_taken!==l.es_taken?tag('Divergent: '+(l.nq_taken?'NQ':'ES')+' only','div'):l.nq_taken?tag('Both took it','quiet'):tag('Neither','quiet');
    return [l.level,num(l.nq_level),l.active?(l.nq_taken?'Taken':'Not taken'):'—',num(l.es_level),l.active?(l.es_taken?'Taken':'Not taken'):'—',st]}));
  chart(d);
  const s=$('sess').value;
  table($('stats'),['Type','Direction','Next','Cases','NQ went that way','95% interval','Base rate','Average NQ move (pts)','Verdict'],
    d.stats.filter(x=>x.session===s).map(x=>[x.type,tag(x.direction,x.direction==='bearish'?'bear':'bull'),x.horizon,x.n,pct(x.hit_rate),x.n?pct(x.ci95[0])+'–'+pct(x.ci95[1]):'—',pct(x.base_rate),num(x.avg_nq_points),x.verdict]));
  table($('recent'),['Confirmed','Type','Divergence','Leader','NQ after '+d.settings.labels[0],'NQ after '+d.settings.labels[1]],
    d.recent.slice(0,40).map(e=>[ny(e.confirmed_at),e.type,tag(e.direction+' · '+e.level,e.direction==='bearish'?'bear':'bull'),e.leader+' (not '+e.laggard+')',...d.settings.horizons.map(h=>{const o=e.outcomes[String(h)];if(!o)return 'pending';const sp=el('span',(o.nq_points>0?'+':'')+num(o.nq_points)+(o.nq_right?' ✓':' ✗'),null,o.nq_right?'ok':'no');return sp})]));
}
function chart(d){
  const box=$('chart');box.textContent='';const rows=d.chart;if(rows.length<2){el('p','No bars yet this session.',box,'muted');return}
  const NS='http://www.w3.org/2000/svg',W=760,H=260,L=46,R=14,T=14,B=28;
  const n0=rows[0][1],e0=rows[0][2];const nq=rows.map(r=>(r[1]/n0-1)*100),es=rows.map(r=>(r[2]/e0-1)*100);
  const lo=Math.min(...nq,...es),hi=Math.max(...nq,...es),span=(hi-lo)||1;
  const X=i=>L+i*(W-L-R)/(rows.length-1),Y=v=>T+(hi-v)*(H-T-B)/span;
  const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.setAttribute('role','img');svg.setAttribute('aria-label','NQ and ES percent change this session');
  const add=(name,attrs,text)=>{const e=document.createElementNS(NS,name);for(const k in attrs)e.setAttribute(k,attrs[k]);if(text)e.textContent=text;svg.append(e);return e};
  for(let k=0;k<=4;k++){const v=lo+span*k/4;add('line',{x1:L,x2:W-R,y1:Y(v),y2:Y(v),stroke:'#e5e5ea'});add('text',{x:L-6,y:Y(v)+4,'text-anchor':'end','font-size':11,fill:'#6e6e73'},v.toFixed(2)+'%')}
  const path=a=>a.map((v,i)=>(i?'L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1)).join('');
  add('path',{d:path(nq),fill:'none',stroke:'#0071e3','stroke-width':1.6});add('path',{d:path(es),fill:'none',stroke:'#ff9f0a','stroke-width':1.6});
  const idx=ts=>{const s=Date.parse(ts)/1000;let best=0;for(let i=0;i<rows.length;i++)if(rows[i][0]<=s)best=i;return best};
  for(const e of d.today){const i=idx(e.confirmed_at);add('line',{x1:X(i),x2:X(i),y1:T,y2:H-B,stroke:e.direction==='bearish'?'#b3261e':'#11734b','stroke-dasharray':'3 3'});add('text',{x:X(i)+3,y:T+10,'font-size':10.5,fill:e.direction==='bearish'?'#b3261e':'#11734b'},e.direction==='bearish'?'▼':'▲')}
  add('text',{x:L,y:H-8,'font-size':11,fill:'#0071e3'},'NQ');add('text',{x:L+30,y:H-8,'font-size':11,fill:'#ff9f0a'},'ES');
  add('text',{x:W-R,y:H-8,'text-anchor':'end','font-size':11,fill:'#6e6e73'},ny(new Date(rows[rows.length-1][0]*1000).toISOString()));
  box.append(svg)}
for(const b of document.querySelectorAll('#tf button'))b.onclick=()=>{tf=b.dataset.v;if(doc)draw()};
$('sess').onchange=()=>{if(doc)draw()};
fetch('data/smt/current.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{doc=d;if(!d.timeframes['5m']&&d.timeframes['1h'])tf='1h';draw()}).catch(()=>{$('status').textContent='The divergence record has not been published yet. It appears after the engine has archived ES bars.'});
})();
