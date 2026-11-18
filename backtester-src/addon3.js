/* ============================== v4: practice drills, checklist gate, tilt, stop management, more levels, data library ============================== */
const NEW_DEF = { newsSlip: 0, limThru: false, beR: 0, trailPts: 0, gate: false, tilt: true };
Object.assign(DEF, NEW_DEF); for (const k in NEW_DEF) if (!(k in S)) S[k] = NEW_DEF[k];
X.dr = 0; X.drillInfo = null; X.drillEnd = 0; X.cool = 0; X.tiltShown = 0; X.rulesNext = ''; X.lastDrillIdx = -1;
const _d3 = X.dump, _l3 = X.load, _r3 = X.reset;
X.dump = () => ({ ..._d3(), dr: X.dr, di: X.drillInfo, de: X.drillEnd });
X.load = x => { _l3(x); X.dr = (x && x.dr) || 0; X.drillInfo = (x && x.di) || null; X.drillEnd = (x && x.de) || 0; };
X.reset = () => { _r3(); X.dr = 0; X.drillInfo = null; X.drillEnd = 0; X.tiltShown = 0; };

/* ---------- fill realism and stop management ---------- */
function newsTicks() { if (!S.newsSlip || !D) return 0; const m = todMin(D.dt[cur]); return ((m >= 510 && m < 512) || (m >= 570 && m < 572)) ? S.newsSlip : 0; }
function manageStop(tr, i) {
  if (tr.entryT === D.t[i]) return; const L = tr.side > 0;
  if (S.beR > 0 && tr.initSL != null && !tr.beDone) {
    const risk = Math.abs(tr.entry - tr.initSL), fav = L ? D.h[i] - tr.entry : tr.entry - D.l[i];
    if (risk > 0 && fav >= S.beR * risk) { const ns = rt(tr.entry); if (tr.sl == null || (L ? ns > tr.sl : ns < tr.sl)) { tr.sl = ns; tr.beDone = true; dirty.pos = dirty.lines = true; toast(`Stop moved to breakeven at ${S.beR}R`); } }
  }
  if (S.trailPts > 0 && tr.sl != null) {
    const ref = L ? D.h[i] : D.l[i], ns = rt(L ? ref - S.trailPts : ref + S.trailPts);
    if (L ? ns > tr.sl : ns < tr.sl) { tr.sl = ns; dirty.pos = dirty.lines = true; }
  }
}
const revFlag = (q, t) => { const l = closed[closed.length - 1]; return !!(l && l.pnl < 0 && t - l.exitT <= 300 && q > l.qty); };

/* ---------- checklist gate, cooldown, tilt ---------- */
const CHK_DEF = ['Higher-timeframe bias is clear', 'I am inside a kill zone', 'Liquidity was swept or price displaced', 'My stop sits beyond structure', 'The risk is the amount I planned'];
const CHK = {
  'Silver Bullet': ['It is inside the 10:00 to 11:00 window', 'A liquidity sweep happened first', 'Displacement left a fair value gap', 'I am not chasing, the gap is where I would enter', 'The risk is the amount I planned'],
  'Unicorn': ['Higher-timeframe bias is clear', 'A breaker block formed after the sweep', 'A fair value gap overlaps the breaker', 'I am inside a kill zone', 'The risk is the amount I planned'],
  'OTE': ['There is a clear impulse leg with displacement', 'Price retraced into the 0.62 to 0.79 zone', 'It is inside a kill zone', 'Bias agrees with the impulse direction', 'The risk is the amount I planned'],
  'Turtle Soup': ['A clear old high or low was taken out', 'Price closed back inside the range', 'There was displacement after the sweep', 'Bias supports the reversal', 'The risk is the amount I planned'],
  'Judas Swing': ['The midnight open is marked', 'Price made a fake move away from it first', 'It reversed with displacement', 'It is inside a London or New York kill zone', 'The risk is the amount I planned'],
  'London Open': ['The Asia range is marked', 'London swept one side of that range', 'Price displaced back through the range', 'Daily bias agrees', 'The risk is the amount I planned']
};
const _submit = submit;
submit = function (side) {
  if (!D) return;
  if (X.cool && Date.now() < X.cool) { toast('Cooling down. Orders are paused for a moment', 'var(--warn)'); return; }
  const rb = riskBlock(); if (rb) { toast(rb, 'var(--warn)'); return; }
  if (S.gate && X.setup && !(S.chOn && X.ch.state !== 'active')) { gateAsk(side); return; }
  _submit(side); X.rulesNext = '';
};
function goSubmit(side, r) { X.rulesNext = r; _submit(side); X.rulesNext = ''; }
function gateAsk(side, then) {
  const L = CHK[X.setup] || CHK_DEF;
  modal('Checklist · ' + X.setup, `<p class="hint" style="margin:0 0 12px">Tick each item that is true on this chart right now. Analytics splits your results by checklists followed and skipped.</p>${L.map(t => `<label class="chk" style="flex-direction:row;gap:8px;margin-bottom:9px"><input type="checkbox" data-ck="1">${esc(t)}</label>`).join('')}`,
    [['Cancel'], ['Skip checklist', () => (then || goSubmit)(side, 'skipped')], ['Place order', () => { if (![...document.querySelectorAll('#mBody [data-ck]')].every(i => i.checked)) { toast('Tick every item, or choose Skip checklist', 'var(--warn)'); return false; } (then || goSubmit)(side, 'followed'); }, 'primary']]);
}
function startCool() {
  X.cool = Date.now() + 60000; pause();
  const t = setInterval(() => { const s = Math.ceil((X.cool - Date.now()) / 1000); if (s <= 0) { clearInterval(t); X.cool = 0; banner(''); toast('Cooldown over'); } else banner(`Cooling down: ${s}s. Slow breath out, then look at the chart again.`); }, 400);
}
const _closeTrade = closeTrade;
closeTrade = function (tr, px, t, reason) { _closeTrade(tr, px, t, reason); if (S.tilt && reason !== 'Challenge breach' && reason !== 'Drill change') tiltCheck(); };
function tiltCheck() {
  let s = 0; for (let i = closed.length - 1; i >= 0 && closed[i].pnl < 0; i--) s++;
  if (s === 0) X.tiltShown = 0; if (s < 3 || s === X.tiltShown) return; X.tiltShown = s; pause();
  modal(`${s} losses in a row`, `<p>Streaks of losses are where decisions tend to get worse. Before the next trade, check whether the setup meets the model, not whether it would win the loss back.</p><p class="hint">A 60-second cooldown pauses new orders while you breathe out slowly and look at the higher timeframe again.</p>${window.top !== window ? '<p class="hint">The Mindset page on Displace has a short reset routine: <a href="index.html#mind" target="_top" style="color:var(--acc)">open it</a>.</p>' : ''}`, [['Keep going'], ['Take 60 seconds', startCool, 'primary']]);
}

/* ---------- practice drills ---------- */
const DRILLS = { 'Silver Bullet': [595, 75, 'the New York AM Silver Bullet hour, 10:00 to 11:00'], 'London Open': [115, 185, 'the London open, 02:00 to 05:00'], 'Judas Swing': [0, 180, 'the midnight open into London, 00:00 to 03:00'], 'Power of 3': [0, 600, 'a full day from midnight to 10:00'], 'Opening Range Gap': [565, 60, 'the New York open, 09:25 to 10:25'], 'First Presented FVG': [565, 60, 'the New York open, 09:25 to 10:25'], 'Turtle Soup': [505, 120, 'the 08:25 to 10:25 window'], 'London Close': [655, 120, 'the London close, 10:55 to 12:55'], 'Bread and Butter': [120, 240, 'London into the early New York morning'], 'Market Maker Model': [0, 600, 'a full day from midnight to 10:00'] };
const drillOf = m => DRILLS[m] || [505, 180, 'a New York morning, 08:25 to 11:25'];
let drCache = { key: '', list: [] };
function drillList(start) {
  const key = D.name + '|' + D.n + '|' + start; if (drCache.key === key) return drCache.list; const out = [];
  for (let i = 400; i < D.n; i++) { const a = todMin(D.dt[i - 1]), b = todMin(D.dt[i]); if (!((a < start && b >= start) || (b < a && (start > a || start <= b)))) continue; const dw = new Date(D.dt[i] * 1000).getUTCDay(); if (dw >= 1 && dw <= 5) out.push(i); }
  drCache = { key, list: out }; return out;
}
function startDrill(model) {
  if (!D) return; if (D.baseSec >= 3600) { toast('Practice windows need intraday data', 'var(--warn)'); return; }
  const [start, len] = drillOf(model), span = Math.ceil(len * 60 / D.baseSec), L = drillList(start).filter(i => i + span + 3 < D.n);
  if (!L.length) { toast('No suitable windows in this dataset'); return; }
  let idx = L[Math.floor(Math.random() * L.length)]; if (L.length > 1) while (idx === X.lastDrillIdx) idx = L[Math.floor(Math.random() * L.length)];
  X.lastDrillIdx = idx; pause();
  for (const tr of trades.slice()) closeTrade(tr, rt(lastPx() - tr.side * slip()), D.t[cur], 'Drill change');
  orders = []; X.dr++; X.setup = model; $('#oSetup').value = model; cur = idx; X.drillEnd = idx + span; X.drillInfo = { model, start, len, idx, t: D.t[idx] };
  dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true }; rebuild(); scheduleSave();
  toast(`Practice window: ${model}, ${fmtET(D.dt[idx], true, true)} ET`);
}
function drillReview() {
  const di = X.drillInfo; pause(); if (!di) return;
  const L = closed.filter(c => (c.dr || 0) === X.dr && c.entryT >= di.t), net = L.reduce((s, c) => s + c.pnl, 0), w = L.filter(c => c.pnl > 0).length, fol = L.filter(c => c.rules === 'followed').length;
  const box = (l, v, c = '') => `<div class="stat"><div class="l">${l}</div><div class="n ${c}">${v}</div></div>`;
  modal('Window finished · ' + di.model,
    (L.length ? `<div class="statgrid">${box('Trades', L.length)}${box('Net', money(net), cls(net))}${box('Win rate', (w / L.length * 100).toFixed(0) + '%')}${box('Checklist followed', fol + ' / ' + L.length)}</div>
      <table><tr><th>Side</th><th>Entry (ET)</th><th>P&amp;L</th><th>R</th><th>Exit</th></tr>${L.map(c => `<tr><td>${c.side > 0 ? 'Long' : 'Short'}</td><td>${fmtET(toET(c.entryT))}</td><td class="${cls(c.pnl)}">${money(c.pnl)}</td><td class="${cls(c.r)}">${c.r == null ? '—' : c.r.toFixed(2) + 'R'}</td><td class="txt mut">${esc(c.reason)}</td></tr>`).join('')}</table>`
      : '<p>No trades in this window. Staying out is a valid result when the model is not there.</p>') + (trades.length ? '<p class="hint" style="margin-top:10px">You still have an open position. It carries into the next window only if you do not start a new one.</p>' : ''),
    [['Close'], ['Next random window', () => startDrill(di.model), 'primary']]);
}
function openDrill() {
  const opts = MODELS.map(m => `<option ${m === (X.setup || 'Silver Bullet') ? 'selected' : ''}>${m}</option>`).join('');
  modal('Practice a model', `<p class="hint" style="margin:0 0 12px">Jumps to a random weekday window from your data where the model is normally traded. The replay pauses when the window ends and shows a short review. Open trades are closed when a new window starts, and your history stays.</p>
    <label class="form" style="display:block"><span class="hint">Model</span><select class="inp" id="drM" style="width:100%;margin:4px 0 8px">${opts}</select></label><div class="hint" id="drDesc"></div>`,
    [['Cancel'], ['End window now', () => { if (X.drillInfo) drillReview(); }], ['Start random window', () => startDrill($('#drM').value), 'primary']]);
  const upd = () => { const d = drillOf($('#drM').value); $('#drDesc').textContent = 'Window: ' + d[2] + '. About ' + d[1] + ' minutes of replay.'; }; $('#drM').onchange = upd; upd();
}
$('#bDrill').onclick = openDrill;
setInterval(() => {
  const el = $('#rDrill'); if (!el || !D) return;
  if (X.drillInfo && X.drillEnd && cur < X.drillEnd) el.textContent = `Drill · ${X.drillInfo.model} · ${X.drillEnd - cur} bars left`; else el.textContent = X.drillInfo ? 'Drill ended' : '';
}, 300);

/* ---------- more chart levels ---------- */
function calcLevelsX() {
  const out = {}; if (!D || D.baseSec >= 3600) return out;
  if (X.ict.rng) {
    const rangeOf = (a, b) => { let h = -Infinity, l = Infinity, got = false; for (let i = cur; i >= 0 && cur - i < 2200; i--) { const m = todMin(D.dt[i]); if (m >= a && m < b) { got = true; if (D.h[i] > h) h = D.h[i]; if (D.l[i] < l) l = D.l[i]; } else if (got) break; } return got ? { h, l } : null; };
    out.asia = rangeOf(1200, 1440); out.lon = rangeOf(120, 300);
  }
  if (X.ict.pw) {
    const wk = s => Math.floor((s - 4) / 7), cw = wk(Math.floor((D.dt[cur] + 21600) / 86400));
    if (!X.pw || X.pw.cw !== cw || X.pw.d !== D) {
      let h = -Infinity, l = Infinity, f = false;
      for (let i = cur; i >= 0 && cur - i < 20000; i--) { const w = wk(Math.floor((D.dt[i] + 21600) / 86400)); if (w === cw - 1) { f = true; if (D.h[i] > h) h = D.h[i]; if (D.l[i] < l) l = D.l[i]; } else if (w < cw - 1) break; }
      X.pw = { cw, d: D, h: f ? h : null, l: f ? l : null };
    }
    out.pwh = X.pw.h; out.pwl = X.pw.l;
  }
  if (X.ict.orb && todMin(D.dt[cur]) >= 570) {
    const day = Math.floor(D.dt[cur] / 86400); let h = -Infinity, l = Infinity, f = false;
    for (let i = cur; i >= 0 && cur - i < 1500; i--) { if (Math.floor(D.dt[i] / 86400) !== day) break; const m = todMin(D.dt[i]); if (m >= 570 && m < 585) { f = true; if (D.h[i] > h) h = D.h[i]; if (D.l[i] < l) l = D.l[i]; } }
    if (f) { out.orh = h; out.orl = l; }
  }
  return out;
}
function lvList(lv) {
  const o = [];
  if (X.ict.lv) o.push([lv.pdh, 'PDH', '#8a93a6'], [lv.pdl, 'PDL', '#8a93a6'], [lv.mo, 'Midnight open', '#a78bfa']);
  if (X.ict.rng) { if (lv.asia) o.push([lv.asia.h, 'Asia H', '#c58af9'], [lv.asia.l, 'Asia L', '#c58af9']); if (lv.lon) o.push([lv.lon.h, 'London H', '#4c8dff'], [lv.lon.l, 'London L', '#4c8dff']); }
  if (X.ict.pw) o.push([lv.pwh, 'PWH', '#f5a524'], [lv.pwl, 'PWL', '#f5a524']);
  if (X.ict.orb) o.push([lv.orh, 'OR high', '#22c38e'], [lv.orl, 'OR low', '#22c38e']);
  return o;
}
let eqC = { k: '', hi: null, lo: null };
function drawEq(P, from, to, n, X0) {
  const k = n + '|' + agg[n - 1].high + '|' + agg[n - 1].low;
  if (eqC.k !== k) { const hi = new Float64Array(n + 1).fill(-Infinity), lo = new Float64Array(n + 1).fill(Infinity); for (let i = n - 1; i >= 0; i--) { hi[i] = Math.max(hi[i + 1], agg[i].high); lo[i] = Math.min(lo[i + 1], agg[i].low); } eqC = { k, hi, lo }; }
  const tol = agg[n - 1].close * 0.00015, sh = [], sl = [];
  for (let j = Math.max(2, from); j <= Math.min(n - 3, to); j++) { const b = agg[j];
    if (b.high > agg[j - 1].high && b.high > agg[j - 2].high && b.high >= agg[j + 1].high && b.high >= agg[j + 2].high) sh.push(j);
    if (b.low < agg[j - 1].low && b.low < agg[j - 2].low && b.low <= agg[j + 1].low && b.low <= agg[j + 2].low) sl.push(j); }
  const one = (arr, hi) => { let cnt = 0;
    for (let x = arr.length - 1; x > 0 && cnt < 5; x--) for (let y = x - 1; y >= 0 && y >= x - 6; y--) {
      const a = arr[y], b = arr[x], pa = hi ? agg[a].high : agg[a].low, pb = hi ? agg[b].high : agg[b].low; if (Math.abs(pa - pb) > tol) continue;
      const lvl = hi ? Math.max(pa, pb) : Math.min(pa, pb), after = hi ? eqC.hi[b + 1] : eqC.lo[b + 1]; if (hi ? after > lvl + tol * 0.5 : after < lvl - tol * 0.5) continue;
      const yy = candle.priceToCoordinate(lvl); if (yy == null) continue; const col = hi ? '#f0516a' : '#22c38e';
      og.strokeStyle = col; og.lineWidth = 1.5; og.setLineDash([6, 3]); og.beginPath(); og.moveTo(X0(a), yy); og.lineTo(P.w, yy); og.stroke(); og.setLineDash([]); og.fillStyle = col; og.fillText(hi ? 'EQH' : 'EQL', X0(a), yy + (hi ? -8 : 10)); cnt++; break;
    } };
  one(sh, true); one(sl, false);
}

/* ---------- data library + multi-file load ---------- */
const LIB = 'mnqreplay.lib';
const libMeta = () => { try { return JSON.parse(localStorage.getItem(LIB) || '[]') || []; } catch (_) { return []; } };
async function libPut(ds) {
  if (ds.kind === 'demo') return; const key = ds.name + '|' + ds.n;
  try { const db = await idb(); await new Promise(r => { const q = db.transaction('ds', 'readwrite').objectStore('ds').put(ds, 'lib:' + key); q.onsuccess = q.onerror = () => r(); });
    const m = libMeta().filter(x => x.key !== key); m.unshift({ key, name: ds.name, n: ds.n, from: fmtET(ds.dt[0], false, true).slice(0, 10), to: fmtET(ds.dt[ds.n - 1], false, true).slice(0, 10) }); localStorage.setItem(LIB, JSON.stringify(m.slice(0, 12))); } catch (_) {}
}
async function libGet(key) { try { const db = await idb(); return await new Promise(res => { const q = db.transaction('ds').objectStore('ds').get('lib:' + key); q.onsuccess = () => res(q.result); q.onerror = () => res(null); }); } catch (_) { return null; } }
async function libDel(key) { try { const db = await idb(); db.transaction('ds', 'readwrite').objectStore('ds').delete('lib:' + key); } catch (_) {} localStorage.setItem(LIB, JSON.stringify(libMeta().filter(x => x.key !== key))); }
async function readFiles(files) {
  const msg = $('#loadMsg');
  try {
    const rows = []; let bad = 0;
    for (const f of files) { if (msg) msg.textContent = 'Reading ' + f.name + '…'; const r = parseCSV(await f.text(), S.csvTz); for (const x of r.rows) rows.push(x); bad += r.bad; }
    const name = files.length > 1 ? files[0].name + ' + ' + (files.length - 1) + ' more' : files[0].name, ds = finalizeDataset(name, rows, 'csv');
    useDataset(ds); closeModal(); toast(`Loaded ${ds.n.toLocaleString()} bars${files.length > 1 ? ' from ' + files.length + ' files' : ''}${bad ? ` (${bad} rows skipped)` : ''}`); idbPut(ds); libPut(ds);
  } catch (err) { if (msg) msg.innerHTML = '<span class="dn">' + esc(err.message) + '</span>'; else toast(err.message, 'var(--warn)'); }
}
const _bd = $('#bData').onclick;
$('#bData').onclick = () => {
  _bd(); const m = libMeta(); if (!m.length) return; const box = document.createElement('div');
  box.innerHTML = '<div style="margin-top:14px;border-top:1px solid var(--line);padding-top:12px"><div class="hint" style="margin-bottom:8px;text-transform:uppercase;letter-spacing:.6px;font-weight:600">Saved on this device</div>' + m.map(x => `<div class="row" style="margin-bottom:6px"><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(x.name)}</b><br><span class="hint">${x.n.toLocaleString()} bars · ${x.from} to ${x.to}</span></span><button class="xs" data-l="load" data-k="${esc(x.key)}">Load</button><button class="xs" data-l="del" data-k="${esc(x.key)}">Remove</button></div>`).join('') + '</div>';
  $('#mBody').appendChild(box);
  box.onclick = async e => { const b = e.target.closest('button[data-l]'); if (!b) return; const key = b.dataset.k;
    if (b.dataset.l === 'del') { await libDel(key); b.closest('.row').remove(); return; }
    b.textContent = 'Loading…'; const ds = await libGet(key); if (!ds) { b.textContent = 'Missing'; return; } useDataset(ds); idbPut(ds); closeModal(); toast(`Loaded ${ds.n.toLocaleString()} bars`); };
};
$('#fileIn').multiple = true;
$('#fileIn').onchange = e => { if (e.target.files.length) readFiles([...e.target.files]); e.target.value = ''; };

/* ---------- sessions: export and import ---------- */
function dlText(name, text, mime) {
  try { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: mime })); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
  catch (_) { modal('Copy this text', `<textarea class="inp" readonly>${esc(text)}</textarea>`, [['Close']]); }
}
const _openS = openSessions;
openSessions = function () {
  _openS(); const row = document.createElement('div'); row.className = 'row'; row.style.marginTop = '14px';
  row.innerHTML = '<button class="btn" id="ssExp">Export all sessions</button><button class="btn" id="ssImp">Import file</button><span class="hint">Backs up sessions as a file you can keep.</span>'; $('#mBody').appendChild(row);
  $('#ssExp').onclick = () => { const L = sessList(); if (!L.length) { toast('Save a session first'); return; } dlText('mnq-replay-sessions.json', JSON.stringify({ app: 'mnq-replay', v: 1, sessions: L }), 'application/json'); };
  $('#ssImp').onclick = () => { const i = document.createElement('input'); i.type = 'file'; i.accept = '.json'; i.onchange = async () => { try { const j = JSON.parse(await i.files[0].text()), arr = Array.isArray(j) ? j : j.sessions; if (!Array.isArray(arr)) throw 0; const have = new Set(sessList().map(s => s.id)); const merged = sessList().concat(arr.filter(s => s && s.id && !have.has(s.id) && s.closed)); localStorage.setItem(LSS, JSON.stringify(merged.slice(0, 40))); toast(`Imported ${merged.length - have.size} session(s)`); openSessions(); } catch (_) { toast('That file is not a session export', 'var(--warn)'); } }; i.click(); };
};
$('#bSess').onclick = () => openSessions();
