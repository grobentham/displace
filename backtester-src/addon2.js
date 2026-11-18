/* ============================== v3: replay transport, rewind, pause rules, second chart ============================== */
X.rp = { kz: false, open: false, news: false, day: false }; X.c2 = { on: false, tf: 3600 };
const _dump = X.dump, _load = X.load;
X.dump = () => ({ ..._dump(), rp: X.rp, c2: X.c2 });
X.load = x => { _load(x); if (x && x.rp) X.rp = { ...X.rp, ...x.rp }; if (x && x.c2) X.c2 = { ...X.c2, ...x.c2 }; applyC2(); };

/* ---------- rewind ---------- */
function rewindTo(idx) {
  if (!D) return; pause(); idx = Math.max(1, Math.min(cur, Math.round(idx))); if (idx === cur) return;
  if (S.chOn) { toast('Rewind is off during a challenge, so results stay honest', 'var(--warn)'); return; }
  const t = D.t[idx], back = new Map(), keep = [];
  const pend = o => { if (o.od && o.od.t <= t) back.set(o.od.id, o.od); };
  for (const c of closed) {
    if ((c.dr || 0) !== (X.dr || 0)) { keep.push(c); continue; }
    if (c.entryT > t) { pend(c); continue; }
    if (c.exitT > t) { const { exit, exitT, reason, pts, gross, comm, pnl, r, note, ...tr } = c; trades.push(tr); } else keep.push(c);
  }
  closed = keep;
  trades = trades.filter(x => { if (x.entryT > t) { pend(x); return false; } return true; });
  orders = orders.filter(o => o.t <= t); for (const o of back.values()) if (!orders.some(q => q.id === o.id)) orders.push(o);
  cur = idx; X.an = -1; dirty = { pos: true, ord: true, hist: true, stats: true, lines: true, markers: true };
  rebuild(true); if ($('#statsPane').classList.contains('on')) renderStats(); scheduleSave();
}
function backCandle() { if (!D) return; const b = bucket(D.dt[cur]); let i = cur; while (i > 1 && bucket(D.dt[i]) === b) i--; rewindTo(i); }

/* ---------- transport bar ---------- */
const rp = $('#rp');
rp.insertBefore($('#bPlay'), $('#rFwdC')); rp.insertBefore($('#bStep'), $('#rFwdC')); rp.insertBefore($('#speed'), $('#rFast'));
rp.appendChild($('#skipSel')); rp.appendChild($('#jumpDt')); rp.appendChild($('#bJump')); $('#clock').style.display = 'none';
$('#bStep').textContent = '›'; $('#bStep').title = 'Forward one bar (→)';
$('#rBack').onclick = () => rewindTo(cur - 1); $('#rBackC').onclick = backCandle; $('#rFwdC').onclick = () => { pause(); stepCandle(); };
function setSpeed(d) { const i = Math.max(0, Math.min(SPEEDS.length - 1, SPEEDS.indexOf(speed) + d)); speed = SPEEDS[i]; $('#speed').value = speed; toast(`Speed ${speed} bar${speed > 1 ? 's' : ''}/s`); scheduleSave(); }
$('#rSlow').onclick = () => setSpeed(-1); $('#rFast').onclick = () => setSpeed(1);
const scrub = $('#rScrub'); let scrubbing = false;
scrub.addEventListener('input', () => { scrubbing = true; $('#rDate').textContent = fmtET(D.dt[+scrub.value], true, true); $('#rDate').classList.add('on'); });
scrub.addEventListener('change', () => { const v = +scrub.value; scrubbing = false; $('#rDate').classList.remove('on'); if (v > cur) jumpTo(v); else if (v < cur) rewindTo(v); });
function syncRp() {
  if (!D) return;
  if (!scrubbing) { if (+scrub.max !== D.n - 1) scrub.max = D.n - 1; if (+scrub.value !== cur) scrub.value = cur; $('#rDate').textContent = fmtET(D.dt[cur], true, true); scrub.style.setProperty('--p', (cur / (D.n - 1) * 100).toFixed(2) + '%'); }
}
/* ---------- pause rules ---------- */
function rpStop(i) {
  if (X.drillEnd && i >= X.drillEnd) { X.drillEnd = 0; setTimeout(drillReview, 60); return 'practice window finished'; }
  if (i < 1 || D.baseSec >= 3600) return null; const a = todMin(D.dt[i - 1]), b = todMin(D.dt[i]);
  const cross = m => (a < m && b >= m) || (b < a && (m > a || m <= b));
  if (X.rp.kz) for (const z of KZ) if (cross(z[0])) return z[2] + ' kill zone';
  if (X.rp.news && cross(510)) return '08:30 news time';
  if (X.rp.open && cross(570)) return '09:30 New York open';
  if (X.rp.day && cross(1080)) return 'New session (18:00)';
  return null;
}
$('#rOpts').onclick = () => {
  const c = (k, l) => `<label class="chk" style="flex-direction:row;gap:8px;margin-bottom:10px"><input type="checkbox" data-r="${k}" ${X.rp[k] ? 'checked' : ''}>${l}</label>`;
  modal('Pause rules', '<p class="hint" style="margin:0 0 12px">While the replay is playing, pause automatically when the clock reaches (New York time):</p>' + c('kz', 'The start of each kill zone (02:00, 08:30, 13:30)') + c('news', '08:30, when most US data is released') + c('open', '09:30, the New York stock open') + c('day', '18:00, the start of a new session') + '<p class="hint">Pausing on fills, stops and targets is the Auto-pause box in the top bar.</p>',
    [['Cancel'], ['Save', () => { document.querySelectorAll('#mBody [data-r]').forEach(i => { X.rp[i.dataset.r] = i.checked; }); $('#rOpts').classList.toggle('primary', Object.values(X.rp).some(Boolean)); scheduleSave(); }, 'primary']]);
};
/* ---------- second chart ---------- */
let chart2 = null, candle2 = null, a2 = [], a2cur = -1, a2key = '';
function bucket2(dt, f) { return f === 86400 ? Math.floor((dt + 21600) / 86400) * 86400 : f === 14400 ? Math.floor((dt + 21600) / 14400) * 14400 - 21600 : Math.floor(dt / f) * f; }
function add2(i, f) { const k = bucket2(D.dt[i], f), h = D.h[i], l = D.l[i]; let b = a2[a2.length - 1]; if (b && b.time === k) { if (h > b.high) b.high = h; if (l < b.low) b.low = l; b.close = D.c[i]; } else a2.push({ time: k, open: D.o[i], high: h, low: l, close: D.c[i] }); }
function sync2() {
  if (!X.c2.on || !D || !chart2) return; const f = X.c2.tf, key = D.name + '|' + D.n + '|' + f;
  if (key === a2key && cur === a2cur) return;
  if (key !== a2key || cur < a2cur || cur - a2cur > 3000) {
    a2 = []; let i0 = Math.max(0, cur - Math.ceil(900 * f / D.baseSec)); const b0 = bucket2(D.dt[i0], f); while (i0 > 0 && bucket2(D.dt[i0 - 1], f) === b0) i0--;
    for (let i = i0; i <= cur; i++) add2(i, f);
    candle2.setData(a2); if (key !== a2key) chart2.timeScale().setVisibleLogicalRange({ from: Math.max(0, a2.length - 90), to: a2.length + 8 });
  } else { const j0 = Math.max(0, a2.length - 1); for (let i = a2cur + 1; i <= cur; i++) add2(i, f); for (let j = j0; j < a2.length; j++) candle2.update(a2[j]); }
  a2key = key; a2cur = cur;
}
function applyC2() {
  if (!D) return; const ok = TFS.filter(x => x[0] >= D.baseSec && x[0] % D.baseSec === 0);
  if (!ok.some(x => x[0] === X.c2.tf)) X.c2.tf = (ok.find(x => x[0] >= 3600) || ok[ok.length - 1])[0];
  $('#chartWrap').classList.toggle('split', X.c2.on); $('#bSplit').classList.toggle('primary', X.c2.on);
  $('#c2tf').innerHTML = ok.map(x => `<option value="${x[0]}" ${x[0] === X.c2.tf ? 'selected' : ''}>${x[1]}</option>`).join('');
  if (X.c2.on && !chart2) {
    chart2 = LWC.createChart($('#c2'), { autoSize: true, layout: { background: { type: 'solid', color: '#0b0d12' }, textColor: '#8a93a6', fontFamily: 'Inter, sans-serif', fontSize: 11 }, grid: { vertLines: { color: '#151923' }, horzLines: { color: '#151923' } }, crosshair: { mode: 0 }, rightPriceScale: { borderColor: '#232835' }, timeScale: { borderColor: '#232835', timeVisible: true, secondsVisible: false, rightOffset: 8, barSpacing: 7 }, localization: { priceFormatter: p => p.toFixed(2) } });
    candle2 = chart2.addCandlestickSeries({ upColor: '#22c38e', downColor: '#f0516a', borderUpColor: '#22c38e', borderDownColor: '#f0516a', wickUpColor: '#22c38e', wickDownColor: '#f0516a', priceFormat: { type: 'price', precision: 2, minMove: 0.25 } });
  }
  a2key = '';
}
$('#bSplit').onclick = () => { X.c2.on = !X.c2.on; applyC2(); scheduleSave(); };
$('#c2tf').onchange = e => { X.c2.tf = +e.target.value; a2key = ''; scheduleSave(); };
(function tick() { requestAnimationFrame(tick); syncRp(); sync2(); })();
document.addEventListener('keydown', e => {
  if (e.target.closest('input,select,textarea') || $('#modal').classList.contains('on') || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? backCandle() : rewindTo(cur - 1); }
  else if (e.key === '+' || e.key === '=' || e.key === ']') setSpeed(1);
  else if (e.key === '-' || e.key === '[') setSpeed(-1);
  else if (/^[1-8]$/.test(e.key)) { const b = document.querySelectorAll('#tfSeg button')[+e.key - 1]; if (b && !b.disabled) b.click(); }
});
