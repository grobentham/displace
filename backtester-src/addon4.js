/* ============================== v5: indicators panel, right-click orders, load from link ============================== */
const NEW5 = { hideE1: false, hideE2: false };
Object.assign(DEF, NEW5); for (const k in NEW5) if (!(k in S)) S[k] = NEW5[k];
X.inds = []; let indNid = 1;
const ICOL = ['#f5a524', '#4c8dff', '#a78bfa', '#22c38e', '#f0516a', '#64d2ff', '#ffd60a'];
const INAME = { ema: 'EMA', sma: 'SMA', bb: 'Bollinger Bands', rsi: 'RSI' };
const _d5 = X.dump, _l5 = X.load;
X.dump = () => ({ ..._d5(), inds: X.inds.map(({ id, type, len, mult, color, on }) => ({ id, type, len, mult, color, on })) });
X.load = x => { _l5(x); for (const i of X.inds) indKill(i); X.inds = ((x && x.inds) || []).map(i => ({ ...i })); indNid = X.inds.reduce((m, i) => Math.max(m, i.id), 0) + 1; };
function indKill(i) { for (const s of (i.ser || [])) { try { chart.removeSeries(s); } catch (_) {} } i.ser = null; i.v = []; }
function indLayout() {
  const rsi = X.inds.some(i => i.type === 'rsi' && i.on);
  chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.08, bottom: rsi ? 0.32 : 0.12 } });
  chart.priceScale('vol').applyOptions({ scaleMargins: rsi ? { top: 0.7, bottom: 0.2 } : { top: 0.84, bottom: 0 } });
  if (rsi) chart.priceScale('rsi').applyOptions({ scaleMargins: { top: 0.82, bottom: 0.02 } });
}
function indSeries(i) {
  if (i.ser) return i.ser; const mk = (o = {}) => chart.addLineSeries({ color: i.color, lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, ...o });
  if (i.type === 'bb') i.ser = [mk({ lineWidth: 1 }), mk({ lineStyle: 2, lineWidth: 1 }), mk({ lineWidth: 1 })];
  else if (i.type === 'rsi') { const s = mk({ priceScaleId: 'rsi', priceFormat: { type: 'price', precision: 1, minMove: 0.1 } }); s.createPriceLine({ price: 70, color: '#3b4357', lineWidth: 1, lineStyle: 2, axisLabelVisible: false }); s.createPriceLine({ price: 30, color: '#3b4357', lineWidth: 1, lineStyle: 2, axisLabelVisible: false }); i.ser = [s]; }
  else i.ser = [mk()];
  return i.ser;
}
function indStep() {
  const j = agg.length - 1; if (j < 0 || !X.inds.length) return;
  for (const i of X.inds) {
    if (j === 0) { i.v = []; i.ag = []; i.al = []; } if (!i.v) { i.v = []; i.ag = []; i.al = []; }
    const k = agg[j].time, c = agg[j].close, n = i.len;
    if (i.type === 'ema') i.v[j] = { time: k, value: emaNext(j ? i.v[j - 1].value : null, c, n) };
    else if (i.type === 'sma' || i.type === 'bb') {
      if (j + 1 < n) { i.v[j] = undefined; continue; }
      let s = 0; for (let q = j - n + 1; q <= j; q++) s += agg[q].close; const m = s / n;
      if (i.type === 'sma') i.v[j] = { time: k, value: m };
      else { let sq = 0; for (let q = j - n + 1; q <= j; q++) sq += (agg[q].close - m) ** 2; const sd = Math.sqrt(sq / n); i.v[j] = { time: k, u: m + i.mult * sd, m, l: m - i.mult * sd }; }
    } else if (i.type === 'rsi') {
      if (j === 0) { i.ag[0] = 0; i.al[0] = 0; i.v[0] = undefined; continue; }
      const ch = c - agg[j - 1].close, g = ch > 0 ? ch : 0, l = ch < 0 ? -ch : 0;
      if (j < n) { i.ag[j] = (i.ag[j - 1] * (j - 1) + g) / j; i.al[j] = (i.al[j - 1] * (j - 1) + l) / j; i.v[j] = undefined; }
      else { i.ag[j] = (i.ag[j - 1] * (n - 1) + g) / n; i.al[j] = (i.al[j - 1] * (n - 1) + l) / n; i.v[j] = { time: k, value: i.al[j] === 0 ? 100 : 100 - 100 / (1 + i.ag[j] / i.al[j]) }; }
    }
  }
}
const _addBase5 = addBase; addBase = function (i) { _addBase5(i); indStep(); };
function indFeed(i, j) { const p = i.v[j]; if (!p) return null; return i.type === 'bb' ? [{ time: p.time, value: p.u }, { time: p.time, value: p.m }, { time: p.time, value: p.l }] : [p]; }
function indSetAll() {
  for (const i of X.inds) {
    const ser = indSeries(i);
    if (!i.on || (i.type === 'rsi' && false)) { ser.forEach(s => s.setData([])); continue; }
    const cols = i.type === 'bb' ? 3 : 1;
    for (let c = 0; c < cols; c++) ser[c].setData((i.v || []).filter(Boolean).map(p => i.type === 'bb' ? { time: p.time, value: c === 0 ? p.u : c === 1 ? p.m : p.l } : p));
  }
  indLayout();
}
const _rebuild5 = rebuild; rebuild = function (k) { _rebuild5(k); indSetAll(); };
const _push5 = pushUpdates; pushUpdates = function (fromJ) {
  _push5(fromJ); if (agg.length - fromJ > 1500) return;
  for (const i of X.inds) { if (!i.on) continue; const ser = indSeries(i); for (let j = Math.max(0, fromJ); j < agg.length; j++) { const f = indFeed(i, j); if (f) f.forEach((p, c) => ser[c].update(p)); } }
};
const _legend5 = updateLegend;
updateLegend = function (b) {
  _legend5(b); if (!b) return; const j = agg.indexOf(b) >= 0 ? agg.indexOf(b) : agg.length - 1, parts = [];
  for (const i of X.inds) { const p = i.on && i.v && i.v[j]; if (!p) continue; parts.push(`<span style="color:${i.color}">${i.type === 'bb' ? 'BB ' + i.len : INAME[i.type] + ' ' + i.len} ${i.type === 'bb' ? fx(p.m) : i.type === 'rsi' ? p.value.toFixed(1) : fx(p.value)}</span>`); }
  if (parts.length) $('#ind').innerHTML += parts.join('');
};
const DEFLEN = { ema: 50, sma: 50, bb: 20, rsi: 14 };
function openInds() {
  const row = (chk, name, extra, rm) => `<div class="irow"><label class="chk" style="flex-direction:row;gap:8px;flex:1;margin:0">${chk}<span>${name}</span></label>${extra}${rm || ''}</div>`;
  const num = (k, v, min, step) => `<input class="inp mono" ${k} type="number" value="${v}" min="${min}" step="${step}" style="width:70px">`;
  const vis1 = S.showEma && !S.hideE1, vis2 = S.showEma && !S.hideE2;
  const swatch = i => `<select class="inp" data-i="${i.id}" data-f="color" style="width:62px;padding:4px">${ICOL.map(c => `<option value="${c}" ${c === i.color ? 'selected' : ''} style="color:${c}">●●</option>`).join('')}</select>`;
  const body = `<div class="hint" style="margin:0 0 8px">Tick to show or hide. Remove deletes an added indicator.</div>
    ${row(`<input type="checkbox" data-b="e1" ${vis1 ? 'checked' : ''}>`, `<span style="color:#f5a524">EMA</span> fast`, num('data-b="ema1"', S.ema1, 1, 1))}
    ${row(`<input type="checkbox" data-b="e2" ${vis2 ? 'checked' : ''}>`, `<span style="color:#4c8dff">EMA</span> slow`, num('data-b="ema2"', S.ema2, 1, 1))}
    ${row(`<input type="checkbox" data-b="vwap" ${S.showVwap ? 'checked' : ''}>`, `<span style="color:#a78bfa">Session VWAP</span>`, '')}
    ${row(`<input type="checkbox" data-b="vol" ${S.showVol ? 'checked' : ''}>`, 'Volume', '')}
    ${X.inds.map(i => row(`<input type="checkbox" data-i="${i.id}" data-f="on" ${i.on ? 'checked' : ''}>`, `${INAME[i.type]}`, num(`data-i="${i.id}" data-f="len"`, i.len, 2, 1) + (i.type === 'bb' ? num(`data-i="${i.id}" data-f="mult"`, i.mult, 0.5, 0.5) : '') + swatch(i), `<button class="xs" data-i="${i.id}" data-f="rm">Remove</button>`)).join('')}
    <div class="irow" style="margin-top:12px;border-top:1px solid var(--line);padding-top:12px"><span class="hint" style="flex:0">Add</span><select class="inp" id="iaT" style="flex:1">${Object.keys(INAME).map(k => `<option value="${k}">${INAME[k]}</option>`).join('')}</select><button class="btn primary" id="iaGo">Add indicator</button></div>
    <p class="hint" style="margin:10px 0 0">RSI draws in its own band at the bottom of the chart. Everything is calculated only from candles that have already played.</p>`;
  modal('Indicators', body, [['Done', null, 'primary']]);
  const mb = $('#mBody'), redo = () => { const y = mb.scrollTop; openInds(); $('#mBody').scrollTop = y; };
  mb.onchange = e => {
    const t = e.target, b = t.dataset.b, id = +t.dataset.i, f = t.dataset.f;
    if (b === 'e1') { if (t.checked) { S.showEma = true; S.hideE1 = false; } else S.hideE1 = true; rebuild(true); }
    else if (b === 'e2') { if (t.checked) { S.showEma = true; S.hideE2 = false; } else S.hideE2 = true; rebuild(true); }
    else if (b === 'vwap') { S.showVwap = t.checked; rebuild(true); } else if (b === 'vol') { S.showVol = t.checked; rebuild(true); }
    else if (b === 'ema1' || b === 'ema2') { S[b] = Math.max(1, Math.round(+t.value) || 1); rebuild(true); }
    else if (id) { const i = X.inds.find(q => q.id === id); if (!i) return;
      if (f === 'on') i.on = t.checked; else if (f === 'len') { i.len = Math.max(2, Math.round(+t.value) || 2); indKill(i); rebuild(true); }
      else if (f === 'mult') { i.mult = Math.max(0.5, +t.value || 2); indKill(i); rebuild(true); } else if (f === 'color') { i.color = t.value; indKill(i); rebuild(true); }
      if (f === 'on') indSetAll(); }
    updateLegend(agg[agg.length - 1]); scheduleSave();
  };
  mb.onclick = e => {
    const t = e.target.closest('button'); if (!t) return;
    if (t.id === 'iaGo') { const type = $('#iaT').value; X.inds.push({ id: indNid++, type, len: DEFLEN[type], mult: 2, color: ICOL[(X.inds.length + 2) % ICOL.length], on: true }); rebuild(true); updateLegend(agg[agg.length - 1]); scheduleSave(); redo(); }
    else if (t.dataset.f === 'rm') { const i = X.inds.find(q => q.id === +t.dataset.i); if (i) { indKill(i); X.inds = X.inds.filter(q => q !== i); indLayout(); updateLegend(agg[agg.length - 1]); scheduleSave(); redo(); } }
  };
}
$('#tInd').onclick = openInds;

/* ---------- right-click / press-and-hold order menu ---------- */
const ctx = document.createElement('div'); ctx.id = 'ctx'; $('#chartWrap').appendChild(ctx);
function ctxClose() { ctx.style.display = 'none'; }
function placeAt(side, price) {
  if (!D) return; if (X.cool && Date.now() < X.cool) { toast('Cooling down. Orders are paused for a moment', 'var(--warn)'); return; }
  const rb = riskBlock(); if (rb) { toast(rb, 'var(--warn)'); return; }
  const type = (side > 0) === (price < lastPx()) ? 'limit' : 'stop';
  const run = (s, r) => { const o = otype, op = $('#oPrice').value; otype = type; $('#oPrice').value = fx(price); X.rulesNext = r || ''; _submit(side); X.rulesNext = ''; otype = o; $('#oPrice').value = op; };
  if (S.gate && X.setup) gateAsk(side, run); else run(side, '');
}
function ctxOpen(cx, cy, y) {
  if (!D || pickMode) return; const p0 = candle.coordinateToPrice(y); if (p0 == null) return; const price = rt(p0), lp = lastPx();
  const d = price - lp, pts = `${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(2)} pts`, items = [];
  if (price < lp) items.push(['Buy limit', 1], ['Sell stop', -1]); else if (price > lp) items.push(['Sell limit', -1], ['Buy stop', 1]);
  ctx.innerHTML = `<div class="ch">${fx(price)} <span>${pts}</span></div>` + items.map(([l, s], k) => `<button data-k="${k}">${l} at ${fx(price)}</button>`).join('') + (items.length ? '<div class="cs">Uses the SL and TP set in the ticket</div>' : '<div class="cs">That is the current price. Use Buy or Sell for a market order</div>') + '<hr><button data-a="line">Draw a horizontal line here</button><button data-a="copy">Copy price</button>';
  const r = $('#chartWrap').getBoundingClientRect(); ctx.style.display = 'block';
  ctx.style.left = Math.max(4, Math.min(cx - r.left, r.width - 230)) + 'px'; ctx.style.top = Math.max(4, Math.min(cy - r.top, r.height - ctx.offsetHeight - 8)) + 'px';
  ctx.onclick = e => { const b = e.target.closest('button'); if (!b) return; ctxClose();
    if (b.dataset.k != null) placeAt(items[+b.dataset.k][1], price);
    else if (b.dataset.a === 'line') { X.draws.push({ id: X.nid++, type: 'h', a: { t: D.t[cur], p: price } }); scheduleSave(); }
    else if (b.dataset.a === 'copy') { try { navigator.clipboard.writeText(fx(price)); toast('Price copied'); } catch (_) {} } };
}
chartEl.addEventListener('contextmenu', e => { e.preventDefault(); if (X.tool !== 'cursor') return; const q = ptOf(e); if (!inPane(q)) return; ctxOpen(e.clientX, e.clientY, q.y); });
let lp5 = null;
chartEl.addEventListener('pointerdown', e => { ctxClose(); if (e.pointerType !== 'touch' || X.tool !== 'cursor') return; lp5 = { x: e.clientX, y: e.clientY, t: setTimeout(() => { if (lp5 && !drag && !X.drag) { const q = ptOf({ clientX: lp5.x, clientY: lp5.y }); if (inPane(q)) ctxOpen(lp5.x, lp5.y, q.y); } lp5 = null; }, 550) }; });
chartEl.addEventListener('pointermove', e => { if (lp5 && Math.hypot(e.clientX - lp5.x, e.clientY - lp5.y) > 8) { clearTimeout(lp5.t); lp5 = null; } });
['pointerup', 'pointercancel'].forEach(ev => chartEl.addEventListener(ev, () => { if (lp5) { clearTimeout(lp5.t); lp5 = null; } }));
document.addEventListener('keydown', e => { if (e.key === 'Escape') ctxClose(); });
document.addEventListener('pointerdown', e => { if (!e.target.closest('#ctx') && !e.target.closest('#chart')) ctxClose(); });

/* ---------- load a dataset from a link ---------- */
const _bd5 = $('#bData').onclick;
$('#bData').onclick = () => {
  _bd5(); const d = $('#drop'); if (!d) return; let last = ''; try { last = localStorage.getItem('mnqreplay.url') || ''; } catch (_) {}
  d.insertAdjacentHTML('afterend', `<div class="row" style="margin-bottom:6px"><input class="inp" id="urlIn" placeholder="Or paste a link to a CSV (a GitHub link works)" value="${esc(last)}" style="flex:1;min-width:0"><button class="btn" id="urlGo">Load link</button></div>`);
  $('#urlGo').onclick = async () => {
    let u = $('#urlIn').value.trim(), msg = $('#loadMsg'); if (!u) return;
    const m = u.match(/^https?:\/\/github\.com\/([^/]+)\/([^/]+)\/(?:blob|raw)\/(.+)$/i); if (m) u = `https://raw.githubusercontent.com/${m[1]}/${m[2]}/${m[3]}`;
    try { localStorage.setItem('mnqreplay.url', $('#urlIn').value.trim()); } catch (_) {}
    try {
      msg.textContent = 'Downloading…'; const r = await fetch(u); if (!r.ok) throw new Error('The link answered with error ' + r.status);
      const blob = await r.blob(); readFiles([new File([blob], decodeURIComponent(u.split('?')[0].split('/').pop() || 'linked.csv'))]);
    } catch (err) { msg.innerHTML = '<span class="dn">' + esc(err.message === 'Failed to fetch' ? 'Could not download that link from here. Download the file and drop it in instead.' : err.message) + '</span>'; }
  };
};
