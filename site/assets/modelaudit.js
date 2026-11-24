'use strict';
(function(){
const $=id=>document.getElementById(id);
const fmt=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(3):'—';
const pct=x=>typeof x==='number'&&Number.isFinite(x)?(x*100).toFixed(1)+'%':'—';
function el(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(parent)parent.append(n);return n}
function table(root,headers){root.replaceChildren();const t=el('table',undefined,root),h=el('tr',undefined,el('thead',undefined,t));headers.forEach(x=>el('th',x,h));return el('tbody',undefined,t)}
function row(b,values){const tr=el('tr',undefined,b);values.forEach(x=>el('td',x,tr))}
fetch('data/validation/models.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{
 $('model-audit-status').textContent='Historical replay calculated '+d.asof+' · No approved event models';
 const b=table($('model-audit-ranges'),['Market','Test N','Original log skill','Price-only log skill','Point MAE','Baseline point MAE','Point MAE skill','80% coverage','Interval score','Baseline interval score','Rolling direction Brier skill','High / low bin skill']);
 for(const [k,r] of Object.entries(d.markets))row(b,[k.toUpperCase(),r.n,pct(r.original_range_stats?.gain),pct(r.log_mse_skill),fmt(r.point_mae),fmt(r.point_mae_baseline),pct(r.point_mae_skill),pct(r.coverage),fmt(r.interval_score),fmt(r.interval_score_baseline),pct(r.direction_rolling_skill),pct(r.high_bin_skill)+' / '+pct(r.low_bin_skill)]);
 const e=table($('model-audit-events'),['Theme','Asset','Test N','Historical calls','Historical hit rate','Coin-flip Brier skill','Training-rate Brier skill','Qualification']);
 for(const r of d.events)row(e,[r.group,r.asset,r.historical_metrics.tested,r.historical_metrics.calls,pct(r.historical_metrics.rate),pct(r.historical_metrics.brierSkill),pct(r.historical_metrics.brierSkillBase),r.historical_candidate?'Historical candidate — suspended':'Not qualified']);
 for(const l of d.limitations)el('li',l,$('model-audit-limits'));
}).catch(()=>{$('model-audit-status').textContent='Model audit has not yet been published or is unavailable.'})
})();