import sys
s=open('/tmp/bt/index.html',encoding='utf-8').read()
addon=open('/tmp/bt2/addon.js',encoding='utf-8').read()
# cache key levels per bar
addon=addon.replace("function calcLevels() {\n  if (!D || D.baseSec >= 86400) return null;","function calcLevels() {\n  if (!D || D.baseSec >= 86400) return null;\n  if (X.lvC && X.lvC.cur === cur && X.lvC.d === D) return X.lvC.v;\n  const v = calcLevels0() || {}; Object.assign(v, calcLevelsX()); X.lvC = { cur, d: D, v }; return v;\n}\nfunction calcLevels0() {")
def rep(a,b,n=1):
    global s
    c=s.count(a)
    if c!=n: sys.exit(f'ANCHOR x{c} (want {n}): {a[:90]!r}')
    s=s.replace(a,b)
CSS='''
#ov{position:absolute;left:0;top:0;z-index:2;pointer-events:none}
#tools{position:absolute;left:8px;top:54px;z-index:4;display:flex;flex-direction:column;gap:2px;background:rgba(18,21,29,.92);border:1px solid var(--line2);border-radius:9px;padding:3px}
#tools button{width:30px;height:28px;border:0;background:transparent;border-radius:6px;color:var(--mut);display:grid;place-items:center;padding:0}
#tools button:hover{background:var(--panel2);color:#fff}
#tools button.on{background:var(--acc);color:#fff}
#tools svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
#tools hr{border:0;border-top:1px solid var(--line2);margin:2px 3px}
#chFill{display:block;height:100%;width:0;border-radius:3px;transition:width .3s}
.chbar{height:6px;border-radius:3px;background:var(--panel2);margin:2px 0 10px;overflow:hidden}
.anwrap{padding:10px 12px}
.anins{display:flex;gap:8px 22px;flex-wrap:wrap;font-size:12px;color:var(--mut);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin-bottom:10px}
.anins b{color:var(--text)}
.angrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:10px}
.an{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--panel)}
.an h4{margin:0;padding:8px 10px;font-size:11px;letter-spacing:.6px;text-transform:uppercase;color:var(--mut);font-weight:600;border-bottom:1px solid var(--line)}
.an th{position:static}
.an .hint{padding:6px 10px}
td.txt{font-family:Inter,sans-serif}
.anbar{display:block;height:8px;border-radius:2px;min-width:2px}
.anbar.u,.rdist i.u,.dayp i.u{background:var(--up)} .anbar.d,.rdist i.d,.dayp i.d{background:var(--dn)}
.rdist{display:flex;gap:6px;align-items:flex-end;height:120px;padding:10px 10px 6px}
.rdist>div{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:2px;font-size:10px;color:var(--mut)}
.rdist i{display:block;width:100%;border-radius:3px 3px 0 0;min-height:2px}
.rdist b{font-family:var(--mono);color:var(--text);font-weight:500;order:-1}
.dayp{display:flex;gap:3px;align-items:flex-end;height:90px;padding:10px}
.dayp>div{flex:1;max-width:22px;height:100%;display:flex;align-items:flex-end}
.dayp i{display:block;width:100%;border-radius:2px;min-height:2px}
select.mini{background:var(--bg);border:1px solid var(--line2);border-radius:5px;color:var(--text);font-size:11px;padding:2px 4px;max-width:140px}
#app{grid-template-rows:auto 1fr 250px;grid-template-columns:minmax(0,1fr) 300px}
.tabs{overflow-x:auto;white-space:nowrap}
#chartWrap,#bottom{min-width:0}
#app.exp{grid-template-rows:auto 1fr 58vh}
#top{flex-wrap:wrap;overflow:visible;min-height:48px;padding:7px 12px;row-gap:7px}
#skipSel{width:96px}
th{white-space:nowrap}
@media (max-width:900px){.angrid{grid-template-columns:1fr}#app,#app.exp{grid-template-rows:auto 60vh auto auto;grid-template-columns:minmax(0,1fr)}#app.exp #bottom{height:70vh}}
'''
rep("\n@media (max-width:900px){\n  html,body", CSS+"\n@media (max-width:900px){\n  html,body")
I=lambda p:f'<svg viewBox="0 0 16 16">{p}</svg>'
TOOLS=f'''<div id="tools">
      <button data-tool="cursor" class="on" title="Select and move (Esc)">{I('<path d="M3 2l9 5-4 1.2L6.6 12z"/>')}</button>
      <button data-tool="h" title="Horizontal line (H)">{I('<path d="M1.5 8h13"/>')}</button>
      <button data-tool="t" title="Trend line (T)">{I('<path d="M2.5 12.5l11-9"/><circle cx="2.5" cy="12.5" r="1.2"/><circle cx="13.5" cy="3.5" r="1.2"/>')}</button>
      <button data-tool="r" title="Zone / rectangle (R)">{I('<rect x="2.5" y="4" width="11" height="8" rx="1"/>')}</button>
      <button data-tool="f" title="Fib retracement with OTE (G)">{I('<path d="M2 3h12M2 6.5h12M2 9.5h12M2 13h12"/>')}</button>
      <button data-tool="m" title="Measure points, bars and dollars (M)">{I('<path d="M3 13L13 3M3 13v-3M3 13h3M13 3v3M13 3h-3"/>')}</button>
      <hr>
      <button id="tDel" title="Delete selected drawing (Del)">{I('<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5"/>')}</button>
      <button id="tClear" title="Clear all drawings">{I('<path d="M4 4l8 8M12 4l-8 8"/>')}</button>
    </div>'''
rep('<div id="chart"></div>','<div id="chart"></div>\n    <canvas id="ov"></canvas>\n    '+TOOLS)
rep('<span class="clock" id="clock">—</span>','''<select class="inp" id="skipSel" title="Skip forward to a time of day (New York time)"><option value="">Skip to…</option><option value="120">London open 02:00</option><option value="510">08:30 news</option><option value="570">NY open 09:30</option><option value="600">Silver Bullet 10:00</option><option value="810">NY PM 13:30</option><option value="900">PM Silver Bullet 15:00</option><option value="day">Next session (18:00)</option></select>
    <span class="clock" id="clock">—</span>''')
rep('<button class="btn" id="bData">Data</button>','<button class="btn" id="bICT">Overlays</button>\n    <button class="btn" id="bChal">Challenge</button>\n    <button class="btn" id="bSess">Sessions</button>\n    <button class="btn" id="bShot" title="Save the chart as an image">Image</button>\n    <button class="btn" id="bData">Data</button>')
rep('''    <div class="card">
      <h3>Order ticket</h3>''','''    <div class="card" id="chCard" style="display:none">
      <h3>Challenge <span id="chState" style="letter-spacing:.5px"></span></h3>
      <div class="chbar"><i id="chFill"></i></div>
      <div class="kv" id="chKv"></div>
    </div>
    <div class="card">
      <h3>Order ticket</h3>''')
rep('''      <div class="preview"><span id="pvRisk">''','''      <div class="row">
        <label>Setup</label>
        <select class="inp" id="oSetup" style="flex:1;min-width:0" title="Tag the next trade with the model you are practising"></select>
      </div>
      <div class="preview"><span id="pvRisk">''')
rep('<button data-p="statsPane">Stats</button>','<button data-p="statsPane">Stats</button>\n      <button data-p="anaPane">Analytics</button>')
rep('<button class="xs" id="bCopyCsv" style="padding:4px 9px">','<button class="xs" id="bExp" style="padding:4px 9px">Expand panel</button>\n      <button class="xs" id="bCopyCsv" style="padding:4px 9px">')
rep('<div class="pane" id="statsPane"></div>','<div class="pane" id="statsPane"></div>\n    <div class="pane" id="anaPane"></div>')
rep('Drag SL / TP / order lines on the chart to move them.','Drag SL / TP / order lines on the chart to move them. Practice tool on historical data only.')

# --- engine hooks
rep("function openTrade(side, qty, px, t, sl, tp, src) {\n  const tr = { id: nextId++, side, qty, entry: px, entryT: t, sl, tp, initSL: sl, mae: 0, mfe: 0, src };",
    "function openTrade(side, qty, px, t, sl, tp, src, model) {\n  const tr = { id: nextId++, side, qty, entry: px, entryT: t, sl, tp, initSL: sl, mae: 0, mfe: 0, src, model: model == null ? X.setup : model, sess: sessOf(t), grade: '' };")
rep("function checkExits(tr, i, sameBar) {","function closePart(tr, q, px, t, reason) {\n  q = Math.floor(q); if (q <= 0) return;\n  if (q >= tr.qty) return closeTrade(tr, px, t, reason);\n  closeTrade({ ...tr, id: nextId++, qty: q }, px, t, reason); tr.qty -= q;\n}\nfunction checkExits(tr, i, sameBar) {")
rep("od.type === 'limit' ? 'limit' : 'stop');","od.type === 'limit' ? 'limit' : 'stop', od.model);")
rep("    ev = true;\n  }\n  return ev;\n}","    ev = true;\n  }\n  if (chBar(i)) ev = true;\n  return ev;\n}")
rep("function submit(side) {\n  if (!D) return;","function submit(side) {\n  if (!D) return;\n  if (S.chOn && X.ch.state !== 'active') { toast(X.ch.state === 'passed' ? 'Challenge passed. Start a new session to trade again' : 'Challenge failed. Start a new session to try again', 'var(--warn)'); return; }")
rep("price, sl, tp, t: D.t[cur] });","price, sl, tp, t: D.t[cur], model: X.setup });")
rep("  if (dirty.pos) ren","  renderChallenge();\n  if (X.an !== closed.length && $('#anaPane').classList.contains('on')) renderAnalytics();\n  if (dirty.pos) ren")
rep("if (b.dataset.p === 'statsPane') renderStats();","if (b.dataset.p === 'statsPane') renderStats();\n  if (b.dataset.p === 'anaPane') renderAnalytics();")
# positions: partial close
rep('''<button class="xs" data-a="close">Close</button></td></tr>`''','''${t.qty > 1 ? '<button class="xs" data-a="half" title="Close half the position">Close ½</button>' : ''}<button class="xs" data-a="close">Close</button></td></tr>`''')
rep("  if (a === 'close') closeTrade(t, rt(lp - t.side * slip()), D.t[cur], 'Manual');","  if (a === 'close') closeTrade(t, rt(lp - t.side * slip()), D.t[cur], 'Manual');\n  if (a === 'half') closePart(t, Math.floor(t.qty / 2), rt(lp - t.side * slip()), D.t[cur], 'Partial');")
# history: setup + grade
rep("<th>MAE/MFE</th><th>Notes</th></tr>","<th>MAE/MFE</th><th>Setup</th><th>Grade</th><th>Notes</th></tr>")
rep('''    <td><input class="note" placeholder="Add a note…" value="${esc(c.note || '')}"></td></tr>`''','''    <td><select class="mini" data-f="model"><option value="">—</option>${MODELS.map(m => `<option ${c.model === m ? 'selected' : ''}>${m}</option>`).join('')}</select></td><td><select class="mini" data-f="grade">${['', 'A', 'B', 'C'].map(g => `<option ${(c.grade || '') === g ? 'selected' : ''} value="${g}">${g || '—'}</option>`).join('')}</select></td>
    <td><input class="note" placeholder="Add a note…" value="${esc(c.note || '')}"></td></tr>`''')
rep("$('#histPane').addEventListener('change', e => {\n  if (!e.target.classList.contains('note')) return;","$('#histPane').addEventListener('change', e => {\n  if (e.target.dataset.f) { const c0 = closed.find(x => x.id === +e.target.closest('tr').dataset.id); if (c0) { c0[e.target.dataset.f] = e.target.value; X.an = -1; scheduleSave(); } return; }\n  if (!e.target.classList.contains('note')) return;")
rep("'mae_pts', 'mfe_pts', 'note'];","'mae_pts', 'mfe_pts', 'setup', 'session', 'grade', 'note'];")
rep("c.mae.toFixed(2), c.mfe.toFixed(2), '\"'","c.mae.toFixed(2), c.mfe.toFixed(2), c.model || '', c.sess || '', c.grade || '', '\"'")
# settings / labels
rep('''<option value="20" ${S.pv == 20 ? 'selected' : ''}>NQ — $20 / point ($5 / tick)</option></select>''','''<option value="20" ${S.pv == 20 ? 'selected' : ''}>NQ — $20 / point ($5 / tick)</option><option value="5" ${S.pv == 5 ? 'selected' : ''}>MES — $5 / point ($1.25 / tick)</option><option value="50" ${S.pv == 50 ? 'selected' : ''}>ES — $50 / point ($12.50 / tick)</option></select>''')
rep("$('#ctrLbl').textContent = S.pv == 20 ? 'NQ $20/pt' : 'MNQ $2/pt';","$('#ctrLbl').textContent = ctrName();",2)
rep("$('#symLbl').textContent = D.kind === 'demo' ? 'MNQ1! · DEMO' : 'MNQ1!';","$('#symLbl').textContent = SYM() + '1!' + (D.kind === 'demo' ? ' · DEMO' : '');")
rep("      dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true };\n      rebuild(true); scheduleSave();","      dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true }; X.an = -1;\n      $('#symLbl').textContent = SYM() + '1!' + (D.kind === 'demo' ? ' · DEMO' : '');\n      rebuild(true); scheduleSave();")
# session state
rep("nextId = 1; dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true }; }","nextId = 1; dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true }; X.reset(); }")
rep("    if (session.curT) cur = idxAt(session.curT);\n  }","    if (session.curT) cur = idxAt(session.curT);\n  }\n  X.load(session && session.X);")
rep("closed, nextId, speed }));","closed, nextId, speed, X: X.dump() }));")
rep('''<span class="kbd">Esc</span><span>Cancel price picking</span></div>''','''<span class="kbd">Esc</span><span>Cancel price picking or drawing</span>
  <span class="kbd">H</span><span>Horizontal line</span><span class="kbd">T</span><span>Trend line</span>
  <span class="kbd">R</span><span>Zone</span><span class="kbd">G</span><span>Fib with OTE</span>
  <span class="kbd">M</span><span>Measure</span><span class="kbd">Del</span><span>Delete selected drawing</span></div>
  <p class="mut" style="font-size:12.5px;line-height:1.55">Drawing tools need two clicks: one to start, one to finish. Click a drawing to select it, drag it to move it, drag a corner handle to resize it.</p>''')
rep("\nwindow.addEventListener('beforeunload', saveNow);","\n"+addon+"\nwindow.addEventListener('beforeunload', saveNow);")
rep("<title>","<title>",1)

rep("\n@media (max-width:900px){\n  html,body", """
#app.focus{grid-template-columns:minmax(0,1fr);grid-template-rows:auto 1fr;grid-template-areas:"top" "chart"}
#app.focus #side,#app.focus #bottom{display:none}
#quick{position:absolute;left:50%;bottom:44px;transform:translateX(-50%);z-index:4;display:none;align-items:center;gap:6px;background:rgba(18,21,29,.94);border:1px solid var(--line2);border-radius:11px;padding:6px;box-shadow:0 10px 30px rgba(0,0,0,.45);white-space:nowrap}
#app.focus #quick{display:flex}
#quick button{border:0;border-radius:7px;padding:7px 14px;font-weight:700;color:#fff}
#quick .qs{background:var(--dn)} #quick .qb{background:var(--up)} #quick .qf{background:var(--panel2);border:1px solid var(--line2);font-weight:500}
#quick input{width:52px;text-align:center}
#quick span{font-family:var(--mono);font-size:12px;padding:0 6px}
@media (max-width:900px){#app.focus{height:100vh;grid-template-rows:auto 1fr}}

@media (max-width:900px){
  html,body""")
rep('<button class="btn" id="bICT">Overlays</button>','<button class="btn" id="bFocus" title="Hide the side and bottom panels so the chart fills the screen (V)">Focus</button>\n    <button class="btn" id="bFs" title="Use the whole screen">Full screen</button>\n    <button class="btn" id="bICT">Overlays</button>')
rep('<div id="toast"></div>','<div id="toast"></div>\n    <div id="quick"><button class="qs" id="qSell">Sell</button><input class="inp mono" id="qQty" type="number" min="1" value="1" title="Contracts"><button class="qb" id="qBuy">Buy</button><button class="qf" id="qFlat">Flatten</button><span id="qPnl"></span></div>')
rep("  renderChallenge();\n","  renderChallenge();\n  if ($('#app').classList.contains('focus')) { const qa = acct(); $('#qPnl').innerHTML = `${qa.net ? (qa.net > 0 ? 'Long ' : 'Short ') + Math.abs(qa.net) : 'Flat'} · <span class=\"${cls(qa.open)}\">${money(qa.open)}</span> · Net <span class=\"${cls(qa.realized)}\">${money(qa.realized)}</span>`; }\n")
rep("\nwindow.addEventListener('beforeunload', saveNow);", """
function setFocus(on) { $('#app').classList.toggle('focus', on); $('#bFocus').classList.toggle('primary', on); $('#bFocus').textContent = on ? 'Show panels' : 'Focus'; $('#qQty').value = $('#oQty').value; try { localStorage.setItem('mnqreplay.focus', on ? '1' : ''); } catch (_) {} renderTick(); }
$('#bFocus').onclick = () => setFocus(!$('#app').classList.contains('focus'));
$('#qQty').oninput = e => { $('#oQty').value = Math.max(1, +e.target.value || 1); updatePreview(); };
$('#qBuy').onclick = () => submit(1); $('#qSell').onclick = () => submit(-1); $('#qFlat').onclick = flatten;
$('#bFs').onclick = () => { const d = document, el = d.documentElement; try { if (d.fullscreenElement || d.webkitFullscreenElement) (d.exitFullscreen || d.webkitExitFullscreen).call(d); else { const r = (el.requestFullscreen || el.webkitRequestFullscreen).call(el); if (r && r.catch) r.catch(() => toast('Full screen is blocked here. Open the backtester in its own tab', 'var(--warn)')); } } catch (_) { toast('Full screen is not available in this browser', 'var(--warn)'); } };
document.addEventListener('keydown', e => { if (e.target.closest('input,select,textarea') || $('#modal').classList.contains('on') || e.metaKey || e.ctrlKey) return; if (e.key === 'v' || e.key === 'V') setFocus(!$('#app').classList.contains('focus')); });
try { if (localStorage.getItem('mnqreplay.focus')) $('#app').classList.add('focus'), $('#bFocus').classList.add('primary'), $('#bFocus').textContent = 'Show panels'; } catch (_) {}

window.addEventListener('beforeunload', saveNow);""")
rep('<span class="kbd">M</span><span>Measure</span>','<span class="kbd">V</span><span>Focus: chart fills the screen</span><span class="kbd">M</span><span>Measure</span>')

addon2=open('/tmp/bt2/addon2.js',encoding='utf-8').read()
rep("\n@media (max-width:900px){\n  html,body", """
#app{grid-template-rows:auto 1fr auto 250px;grid-template-areas:"top top" "chart side" "rp side" "bottom side"}
#app.exp{grid-template-rows:auto 1fr auto 58vh}
#app.focus{grid-template-rows:auto 1fr auto;grid-template-areas:"top" "chart" "rp"}
#rp{grid-area:rp;display:flex;align-items:center;gap:6px;padding:6px 10px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:var(--panel);min-width:0}
#rp .btn.icon{min-width:32px;font-size:15px;line-height:1}
#rp .sep{margin:0 4px}
#rScrub{flex:1;min-width:60px;height:4px;-webkit-appearance:none;appearance:none;border-radius:2px;outline:none;background:linear-gradient(90deg,var(--acc) var(--p,0%),var(--line2) var(--p,0%));cursor:pointer}
#rScrub::-webkit-slider-thumb{-webkit-appearance:none;width:13px;height:13px;border-radius:50%;background:#fff;border:2px solid var(--acc)}
#rScrub::-moz-range-thumb{width:11px;height:11px;border-radius:50%;background:#fff;border:2px solid var(--acc)}
#rDate{font-family:var(--mono);font-size:11.5px;color:var(--mut);white-space:nowrap;min-width:168px;text-align:right}
#rDate.on{color:#fff}
#top .sep:has(+ .sep),#top .sep:has(+ .chk){display:none}
@media (max-width:900px){#rp #jumpDt,#rp #bJump{display:none}}
#c2box{display:none;position:absolute;left:50%;right:0;top:0;bottom:0;border-left:1px solid var(--line2);z-index:3;background:var(--bg)}
#c2{position:absolute;inset:0}
#c2tf{position:absolute;left:8px;top:8px;z-index:2}
#chartWrap.split #chart{right:50%}
#chartWrap.split #c2box{display:block}
#chartWrap.split #toast{right:calc(50% + 86px)}
#chartWrap.split #quick{left:25%}
@media (max-width:900px){#app,#app.exp{grid-template-rows:auto 60vh auto auto auto;grid-template-areas:"top" "chart" "rp" "side" "bottom"}#app.focus{grid-template-rows:auto 1fr auto}#rDate{display:none}#bSplit{display:none}#chartWrap.split #chart{right:0}#chartWrap.split #c2box{display:none}#rp{flex-wrap:wrap}}

@media (max-width:900px){
  html,body""")
rep('  <div id="side">','  <div id="rp"><button class="btn icon" id="rBackC" title="Back one candle (Shift+←)">«</button><button class="btn icon" id="rBack" title="Back one bar (←)">‹</button><button class="btn icon" id="rFwdC" title="Forward to the end of this candle (Shift+→)">»</button><div class="sep"></div><button class="btn icon" id="rSlow" title="Slower (−)">−</button><button class="btn icon" id="rFast" title="Faster (+)">+</button><div class="sep"></div><input type="range" id="rScrub" min="1" max="100" value="1" step="1" title="Drag to move through the data"><span id="rDate"></span><button class="btn" id="rOpts" title="Choose when the replay pauses by itself">Pause rules</button></div>\n\n  <div id="side">')
rep('<div id="toast"></div>','<div id="toast"></div>\n    <div id="c2box"><div id="c2"></div><select class="inp" id="c2tf" title="Timeframe of the second chart"></select></div>')
rep('<button class="btn" id="bICT">Overlays</button>','<button class="btn" id="bSplit" title="Show a second chart on another timeframe">2 charts</button>\n    <button class="btn" id="bICT">Overlays</button>')
rep("    if (processBar(cur)) { ev = true; if (playing && $('#stopOnFill').checked) { pause(); break; } }","    if (processBar(cur)) { ev = true; if (playing && $('#stopOnFill').checked) { pause(); break; } }\n    if (playing) { const why = rpStop(cur); if (why) { pause(); toast('Paused: ' + why); break; } }")
rep("od.type === 'limit' ? 'limit' : 'stop', od.model);","od.type === 'limit' ? 'limit' : 'stop', od.model); tr.od = od;")
rep("  const doIt = () => { resetSession(false); cur = idx; rebuild(); scheduleSave(); };","  if (!S.chOn) { rewindTo(idx); return; }\n  const doIt = () => { resetSession(false); cur = idx; rebuild(); scheduleSave(); };")
rep("\nfunction setFocus(on)","\n"+addon2+"\nfunction setFocus(on)")
rep('<span class="kbd">V</span>','<span class="kbd">←</span><span>Back one bar. Shift + ← goes back one candle</span><span class="kbd">+ / −</span><span>Faster or slower replay</span><span class="kbd">1 – 8</span><span>Switch timeframe</span><span class="kbd">V</span>')
rep("All times are New York time;","Going back in time reopens trades that had closed after that point, removes trades entered after it, and restores orders that had not filled yet. All times are New York time;")

rep("</style>", """@media (max-width:900px){
  #app,#app.exp{grid-template-columns:minmax(0,1fr);grid-template-rows:auto 60vh auto auto auto;grid-template-areas:"top" "chart" "rp" "side" "bottom"}
  #app.focus{height:100vh;height:100dvh;grid-template-rows:auto 1fr auto;grid-template-areas:"top" "chart" "rp"}
  #rp{row-gap:6px}#rScrub{flex-basis:100%;order:9;margin:4px 2px}
}
</style>""")

addon3=open('/tmp/bt2/addon3.js',encoding='utf-8').read()
rep("\nfunction setFocus(on)","\n"+addon3+"\nfunction setFocus(on)")
rep("const slip = () => S.slipTicks * TICK;","const slip = () => (S.slipTicks + newsTicks()) * TICK;")
rep("      if (od.side > 0 && l <= od.price) px = Math.min(o, od.price);\n      if (od.side < 0 && h >= od.price) px = Math.max(o, od.price);","      if (od.side > 0 && l <= od.price - (S.limThru ? TICK : 0)) px = Math.min(o, od.price);\n      if (od.side < 0 && h >= od.price + (S.limThru ? TICK : 0)) px = Math.max(o, od.price);")
rep("  if (chBar(i)) ev = true;\n  return ev;","  for (const tr of trades) manageStop(tr, i);\n  if (chBar(i)) ev = true;\n  return ev;")
rep("sess: sessOf(t), grade: '' };","sess: sessOf(t), grade: '', rules: X.rulesNext || '', rev: revFlag(qty, t), dr: X.dr || 0 };")
rep("  trades.push(tr);\n  toast(`${side > 0 ? 'Bought'","  trades.push(tr);\n  if (tr.rev && S.tilt) toast('Bigger size right after a loss. Check this is the model, not the loss.', 'var(--warn)');\n  toast(`${side > 0 ? 'Bought'")
rep("od.model); tr.od = od;","od.model); tr.od = od; tr.rules = od.rules || '';")
rep("price, sl, tp, t: D.t[cur], model: X.setup });","price, sl, tp, t: D.t[cur], model: X.setup, rules: X.rulesNext });")
rep("${f('ema1', 'Fast EMA length')}${f('ema2', 'Slow EMA length')}","""${f('newsSlip', 'Extra slippage at 08:30 and 09:30 (ticks)', 'number', 'step="1" min="0"')}${f('beR', 'Move stop to breakeven at (R, 0 = off)', 'number', 'step="0.25" min="0"')}
    ${f('trailPts', 'Trailing stop distance (points, 0 = off)', 'number', 'step="0.25" min="0"')}<div></div>
    <div class="full">${c('limThru', 'Limit orders only fill once price trades one tick through them')}</div>
    <div class="full" style="display:flex;gap:18px;flex-wrap:wrap">${c('gate', 'Ask for the model checklist before each tagged entry')}${c('tilt', 'Tilt warnings after losing streaks')}</div>
    ${f('ema1', 'Fast EMA length')}${f('ema2', 'Slow EMA length')}""")
rep("'setup', 'session', 'grade', 'note'];","'setup', 'session', 'grade', 'checklist', 'note'];")
rep("c.model || '', c.sess || '', c.grade || '', '\"'","c.model || '', c.sess || '', c.grade || '', c.rules || '', '\"'")
rep('accept=".csv,.txt"','accept=".csv,.txt" multiple')
rep("if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]);","if (e.dataTransfer.files.length) readFiles([...e.dataTransfer.files]);")
rep("<b>Drop a CSV here</b>","<b>Drop one or more CSV files here</b>")
rep("1-minute bars recommended · higher timeframes are built from them","1-minute bars recommended · several files are joined into one dataset")
rep('<button class="btn" id="rOpts"','<span id="rDrill" class="mut" style="font-size:11.5px;white-space:nowrap"></span><button class="btn" id="rOpts"')
rep('<button class="btn" id="bSess">Sessions</button>','<button class="btn" id="bDrill" title="Jump to random windows where a model is normally traded">Practice</button>\n    <button class="btn" id="bSess">Sessions</button>')
rep("drag a corner handle to resize it.</p>","drag a corner handle to resize it.</p><p class='mut' style='font-size:12.5px;line-height:1.55'><b>Practice</b> jumps to random windows where a model is normally traded and reviews your trades when the window ends. In Settings you can turn on a checklist before each tagged entry, tilt warnings, auto breakeven, a trailing stop, news-time slippage and stricter limit fills. Overlays adds Asia and London ranges, previous week high and low, the opening range and equal highs and lows.</p>")

rep("</style>", """#top{gap:6px}
#top .btn{padding:5px 9px;font-size:12.5px}
#top .sym{padding:4px 7px}
#rp .btn{white-space:nowrap}
#rDate{min-width:0;flex:none;text-align:left}
#rp #jumpDt{width:138px}
#rp #speed{width:88px}
#rScrub{min-width:70px}
#rDrill{flex:none}
#rp:has(#rDrill:not(:empty)) #jumpDt,#rp:has(#rDrill:not(:empty)) #bJump{display:none}
#rDrill:empty{display:none}
#rDrill{max-width:200px;overflow:hidden;text-overflow:ellipsis}
</style>""")

addon4=open('/tmp/bt2/addon4.js',encoding='utf-8').read()
rep("\nfunction setFocus(on)","\n"+addon4+"\nfunction setFocus(on)")
rep("ema1S.setData(S.showEma ? e1 : []); ema2S.setData(S.showEma ? e2 : []);","ema1S.setData(S.showEma && !S.hideE1 ? e1 : []); ema2S.setData(S.showEma && !S.hideE2 ? e2 : []);")
rep("    if (S.showEma) { ema1S.update(e1[j]); ema2S.update(e2[j]); }","    if (S.showEma) { if (!S.hideE1) ema1S.update(e1[j]); if (!S.hideE2) ema2S.update(e2[j]); }")
rep("  if (S.showEma && e1[j]) parts.push(`<span style=\"color:#f5a524\">EMA ${S.ema1} ${fx(e1[j].value)}</span>`, `<span style=\"color:#4c8dff\">EMA ${S.ema2} ${fx(e2[j].value)}</span>`);","  if (S.showEma && e1[j]) { if (!S.hideE1) parts.push(`<span style=\"color:#f5a524\">EMA ${S.ema1} ${fx(e1[j].value)}</span>`); if (!S.hideE2) parts.push(`<span style=\"color:#4c8dff\">EMA ${S.ema2} ${fx(e2[j].value)}</span>`); }")
rep('<path d="M4 4l8 8M12 4l-8 8"/></svg></button>','<path d="M4 4l8 8M12 4l-8 8"/></svg></button>\n      <hr><button id="tInd" title="Indicators: add or remove" style="font:700 11px var(--mono)">fx</button>')
rep("Drag SL / TP / order lines on the chart to move them. Practice tool on historical data only.","Right-click the chart (press and hold on a phone) to place a limit or stop order at that price. Drag SL / TP / order lines to move them. Practice tool on historical data only.")
rep("</style>","""#ctx{display:none;position:absolute;z-index:6;width:220px;background:#12151d;border:1px solid var(--line2);border-radius:10px;padding:5px;box-shadow:0 14px 40px rgba(0,0,0,.55)}
#ctx .ch{padding:6px 9px;font-family:var(--mono);font-size:12.5px;color:#fff;font-weight:600}#ctx .ch span{color:var(--mut);font-weight:400;margin-left:6px}
#ctx button{display:block;width:100%;text-align:left;border:0;background:transparent;color:var(--text);padding:8px 9px;border-radius:6px;font-size:13px}
#ctx button:hover{background:var(--panel2)}
#ctx .cs{padding:2px 9px 6px;font-size:11px;color:var(--dim)}
#ctx hr{border:0;border-top:1px solid var(--line);margin:4px 2px}
.irow{display:flex;align-items:center;gap:8px;margin-bottom:8px}
</style>""")
rep('<span class="kbd">V</span>','<span class="kbd">Right-click</span><span>On the chart: place a limit or stop order at that price</span><span class="kbd">V</span>')

rep('<button class="btn" id="bSess">Sessions</button>','<button class="btn" id="bStrat" title="Build rules from conditions and test them on the loaded data">Strategy</button>\n    <button class="btn" id="bSess">Sessions</button>')
addon6=open('/tmp/bt2/addon6.js',encoding='utf-8').read()
rep("\nfunction setFocus(on)","\n"+addon6+"\nfunction setFocus(on)")
rep("</style>",""".stb h4{margin:14px 0 6px;font-size:11px;letter-spacing:.6px;text-transform:uppercase;color:var(--muted,#8b93a7);font-weight:600}
.strow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}.stl{font-size:12px;color:var(--muted,#8b93a7)}
.stgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:6px}.sttile{padding:8px 10px;border:1px solid var(--line);border-radius:10px}.sttile .mono{font-size:14px;margin-top:2px}
@media (max-width:700px){.stgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>""")

addon5=open('/tmp/bt2/addon5.js',encoding='utf-8').read()
rep("\nfunction setFocus(on)","\n"+addon5+"\nfunction setFocus(on)")
rep("<th>Setup</th><th>Grade</th><th>Notes</th></tr>","<th>Setup</th><th>Grade</th><th></th><th>Notes</th></tr>")
rep('<td><input class="note" placeholder="Add a note…"','<td><button class="xs" data-v="${c.id}" title="Show this trade on the chart">View</button></td><td><input class="note" placeholder="Add a note…"')
rep("function manageStop(tr, i) {\n  if (tr.entryT === D.t[i]) return; const L = tr.side > 0;","function manageStop(tr, i) {\n  if (tr.entryT === D.t[i]) return; const L = tr.side > 0; scaleOut(tr, i);")
rep("rev: revFlag(qty, t), dr: X.dr || 0 };","rev: revFlag(qty, t), dr: X.dr || 0, sc: scNow() };")
rep("tr.rules = od.rules || '';","tr.rules = od.rules || ''; tr.sc = od.sc || null;")
rep("model: X.setup, rules: X.rulesNext });","model: X.setup, rules: X.rulesNext, sc: scNow() });")
rep('      <div class="row">\n        <label>Setup</label>','      <div class="row" title="With 2 or more contracts, close part of the position at a first target and move the stop to breakeven">\n        <label class="chk"><input type="checkbox" id="scOn">Scale out</label>\n        <input class="inp mono" id="scPts" type="number" value="20" step="0.25" min="0.25" style="width:64px"><span class="hint">pts</span>\n        <input class="inp mono" id="scPct" type="number" value="50" step="10" min="10" max="90" style="width:54px"><span class="hint">%</span>\n      </div>\n      <div class="row">\n        <label>Setup</label>')
rep("${f('newsSlip', 'Extra slippage at 08:30 and 09:30 (ticks)'","<div class=\"full hint\" style=\"margin-top:4px;text-transform:uppercase;letter-spacing:.6px;font-weight:600\">Your own trading rules</div>\n    ${f('maxTrades', 'Max trades per day (0 = no limit)', 'number', 'step=\"1\" min=\"0\"')}${f('dayLoss', 'Stop for the day after losing ($, 0 = off)', 'number', 'step=\"50\" min=\"0\"')}\n    <div class=\"full\">${c('kzOnly', 'Only allow new orders inside the kill zones')}</div>\n    <div class=\"full hint\" style=\"margin-top:4px;text-transform:uppercase;letter-spacing:.6px;font-weight:600\">Fills and stops</div>\n    ${f('newsSlip', 'Extra slippage at 08:30 and 09:30 (ticks)'")


import re as _re
_a=s.index('    <button class="btn" id="bFocus"'); _b=s.index('<button class="btn icon" id="bHelp" title="Shortcuts">?</button>')+len('<button class="btn icon" id="bHelp" title="Shortcuts">?</button>')
_blk=s[_a:_b]
def _pick(i):
    m=_re.search(r'    <button[^\n]*id="'+i+r'"[^\n]*</button>\n?',_blk); return m.group(0).strip()
_ids=['bFs','bSplit','bChal','bDrill','bSess','bShot','bData','bNew','bHelp']
_menu='\n'.join('      '+_pick(i).replace('class="btn icon"','class="btn"').replace('class="btn"','class="mi"').replace('>?<','>Shortcuts<') for i in _ids)
_new='''    <button class="btn" id="bFocus" title="Hide the side and bottom panels so the chart fills the screen (V)">Focus</button>
    '''+_pick('bStrat')+'''
    '''+_pick('bICT')+'''
    '''+_pick('bSettings')+'''
    <div class="morewrap"><button class="btn icon" id="bMore" title="More tools" aria-haspopup="true">⋯</button>
    <div id="moreMenu" hidden>
'''+_menu+'''
    </div></div>'''
s=s[:_a]+_new+s[_b:]
s=s.replace('</style>','''#top .morewrap{position:relative}
#moreMenu{position:absolute;right:0;top:calc(100% + 8px);z-index:60;min-width:190px;padding:6px;background:var(--panel2,#161a23);border:1px solid var(--line);border-radius:12px;box-shadow:0 18px 40px rgba(0,0,0,.5);display:flex;flex-direction:column}
#moreMenu[hidden]{display:none}
#moreMenu .mi{all:unset;box-sizing:border-box;cursor:pointer;padding:8px 12px;border-radius:8px;font-size:13px;color:var(--text);display:block}
#moreMenu .mi:hover{background:rgba(255,255,255,.07)}
#moreMenu .mi.primary{color:var(--accent,#4c8dff)}
#bMore{font-size:18px;line-height:1;padding:3px 11px}
</style>''',1)
s=s.replace('</script>','''
(function(){const mb=document.getElementById('bMore'),mm=document.getElementById('moreMenu');
mb.onclick=e=>{e.stopPropagation();mm.hidden=!mm.hidden};
mm.addEventListener('click',()=>{setTimeout(()=>{mm.hidden=true},0)});
document.addEventListener('click',e=>{if(!mm.contains(e.target))mm.hidden=true});
document.addEventListener('keydown',e=>{if(e.key==='Escape')mm.hidden=true});})();
</script>''',1) if False else s
_i=s.rindex('</script>'); s=s[:_i]+'''
(function(){const mb=document.getElementById('bMore'),mm=document.getElementById('moreMenu');
mb.onclick=e=>{e.stopPropagation();mm.hidden=!mm.hidden};
mm.addEventListener('click',()=>{setTimeout(()=>{mm.hidden=true},0)});
document.addEventListener('click',e=>{if(!mm.contains(e.target))mm.hidden=true});
document.addEventListener('keydown',e=>{if(e.key==='Escape')mm.hidden=true});})();
'''+s[_i:]


_o1='''      <div class="row">
        <label class="chk"><input type="checkbox" id="slOn" checked>SL pts</label>
        <input class="inp mono" id="oSL" type="number" value="20" step="0.25" min="0.25">
      </div>
      <div class="row">
        <label class="chk"><input type="checkbox" id="tpOn" checked>TP pts</label>
        <input class="inp mono" id="oTP" type="number" value="40" step="0.25" min="0.25">
      </div>'''
assert s.count(_o1)==1
s=s.replace(_o1,'''      <div class="row2">
        <div><label class="chk"><input type="checkbox" id="slOn" checked>Stop</label><input class="inp mono" id="oSL" type="number" value="20" step="0.25" min="0.25" title="Stop distance in points"></div>
        <div><label class="chk"><input type="checkbox" id="tpOn" checked>Target</label><input class="inp mono" id="oTP" type="number" value="40" step="0.25" min="0.25" title="Target distance in points"></div>
      </div>''')
s=s.replace('</style>','''.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.row2>div{display:flex;flex-direction:column;gap:5px;min-width:0}
.row2 .inp{width:100%;min-width:0}
#side .card .row{margin-bottom:6px}
#side .card>.hint[style*='margin-top:10px']{display:none}
</style>''',1)

open('/tmp/bt2/backtest.html','w',encoding='utf-8').write(s)
print('ok',len(s))
