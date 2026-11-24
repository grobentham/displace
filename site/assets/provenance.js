'use strict';
(function(){
const $=id=>document.getElementById(id),repo='https://github.com/grobentham/displace/';
function el(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(parent)parent.append(n);return n}
function link(parent,text,url){const a=el('a',text,parent);a.href=url;return a}
fetch('data/provenance/current.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{
 if(!/^\d+-\d+$/.test(d.id)||d.manifest_path!=='research/provenance/runs/'+d.id+'.json')throw Error('manifest identity');
 $('provenance-status').textContent='Capture '+d.id+' · '+d.asof+' · '+d.total_files+' files · '+(d.total_bytes/1e6).toFixed(2)+' MB of referenced bytes';
 const root=$('provenance-details');el('p','Manifest SHA-256: '+d.manifest_sha256,root).className='dp-hash';
 const links=el('p',undefined,root);link(links,'Archived manifest',repo+'blob/main/'+d.manifest_path);el('span',' · ',links);link(links,'Find the capture commit',repo+'commits/main/'+d.manifest_path);el('span',' · ',links);link(links,'Workflow run',repo+'actions/runs/'+d.id.split('-')[0]);
 el('p','Checkout commit (before the capture was saved): '+d.checkout_commit,root).className='dp-hash';
 if(d.previous)el('p','Previous capture: '+d.previous.id+' · SHA-256 '+d.previous.sha256,root).className='dp-hash';
 const t=el('table',undefined,$('provenance-groups')),h=el('tr',undefined,el('thead',undefined,t));['File group','Files','Referenced bytes'].forEach(x=>el('th',x,h));const body=el('tbody',undefined,t);for(const [k,v] of Object.entries(d.groups)){const tr=el('tr',undefined,body);[k,v.files,v.bytes.toLocaleString()].forEach(x=>el('td',x,tr))}
 el('p','Compared with prior checkout: '+d.changes.new_to_cache+' new-to-cache keys · '+d.changes.revised+' changed keys · '+d.changes.removed+' removed keys · '+d.baseline_series+' newly baselined series.',root);
 el('p',d.policy,root).className='muted';
}).catch(()=>{$('provenance-status').textContent='Provenance has not yet been published or is temporarily unavailable.'})
})();