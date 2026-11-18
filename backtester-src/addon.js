/* ============================== v2: drawings, ICT overlays, tags, analytics, challenge, sessions ============================== */
const MODELS = ['2022 Mentorship', 'Silver Bullet', 'Unicorn', 'OTE', 'Turtle Soup', 'Judas Swing', 'London Open', 'Power of 3', 'One Shot One Kill', 'Opening Range Gap', 'IOFED', 'Bread and Butter', 'Inversion FVG', 'Market Maker Model', 'London Close', 'Breaker', 'New Week Opening Gap', 'First Presented FVG', 'CISD', 'Other'];
const CH_DEF = { chOn: false, chTarget: 3000, chMaxDD: 2000, chType: 'trailing', chDaily: 0, chMinDays: 0 };
Object.assign(DEF, CH_DEF); for (const k in CH_DEF) if (!(k in S)) S[k] = CH_DEF[k];
const X = { draws: [], nid: 1, setup: '', ict: { kz: true, lv: true, fvg: false }, ch: { state: 'off', reason: '', peak: 0 }, tool: 'cursor', pend: null, sel: null, drag: null, busy: false, an: -1 };
const SYMS = { 2: 'MNQ', 20: 'NQ', 5: 'MES', 50: 'ES' };
const SYM = () => SYMS[S.pv] || 'MNQ';
const ctrName = () => `${SYM()} $${S.pv}/pt`;
const todMin = dt => (((dt % 86400) + 86400) % 86400) / 60;
function sessOf(tUTC) { const m = todMin(toET(tUTC)); return (m >= 1080 || m < 120) ? 'Asia' : m < 420 ? 'London' : m < 720 ? 'NY AM' : m < 1020 ? 'NY PM' : 'Other'; }

X.dump = () => ({ draws: X.draws, nid: X.nid, setup: X.setup, ict: X.ict, ch: X.ch });
X.load = x => {
  X.draws = (x && x.draws) || []; X.nid = (x && x.nid) || 1; X.setup = (x && x.setup) || ''; X.sel = X.pend = X.drag = null;
  if (x && x.ict) X.ict = { ...X.ict, ...x.ict };
  if (x && x.ch) X.ch = { ...X.ch, ...x.ch };
  if (!S.chOn) X.ch.state = 'off'; else if (X.ch.state === 'off') { X.ch.state = 'active'; X.ch.peak = S.balance; }
  const sel = $('#oSetup'); if (sel) sel.value = X.setup;
};
X.reset = () => { X.ch = { state: S.chOn ? 'active' : 'off', reason: '', peak: S.balance }; X.an = -1; };

/* ---------- overlay canvas + coordinates ---------- */
const ov = $('#ov'), og = ov.getContext('2d');
function pane() { let w, h; try { w = chart.timeScale().width(); h = chartEl.clientHeight - chart.timeScale().height(); } catch (_) { w = chartEl.clientWidth - 62; h = chartEl.clientHeight - 26; } return { w, h }; }
function xOfT(t) {
  const n = agg.length; if (!n) return null;
  let lg; const first = agg[0].time, last = agg[n - 1].time;
  if (t > last) lg = (n - 1) + (t - last) / tf; else if (t < first) lg = (t - first) / tf;
  else { let lo = 0, hi = n - 1; lg = 0; while (lo <= hi) { const m = (lo + hi) >> 1; if (agg[m].time <= t) { lg = m; lo = m + 1; } else hi = m - 1; } }
  return chart.timeScale().logicalToCoordinate(lg);
}
function tOfX(x) {
  const n = agg.length, lg = chart.timeScale().coordinateToLogical(x); if (lg == null || !n) return null;
  const j = Math.round(lg);
  return j < 0 ? agg[0].time + j * tf : j > n - 1 ? agg[n - 1].time + (j - (n - 1)) * tf : agg[j].time;
}
const ptXY = pt => { const x = xOfT(pt.t), y = candle.priceToCoordinate(pt.p); return (x == null || y == null) ? null : { x, y }; };

function calcLevels() {
  if (!D || D.baseSec >= 86400) return null;
  const dk = Math.floor((D.dt[cur] + 21600) / 86400), cd = Math.floor(D.dt[cur] / 86400);
  let pdh = -Infinity, pdl = Infinity, moI = -1, prev = null;
  for (let i = cur; i >= 0 && cur - i < 6000; i--) {
    const k = Math.floor((D.dt[i] + 21600) / 86400);
    if (k === dk) { if (Math.floor(D.dt[i] / 86400) === cd) moI = i; continue; }
    if (prev == null) prev = k; if (k !== prev) break;
    if (D.h[i] > pdh) pdh = D.h[i]; if (D.l[i] < pdl) pdl = D.l[i];
  }
  const mo = moI >= 0 && todMin(D.dt[moI]) < 30 ? D.o[moI] : null;
  return { pdh: isFinite(pdh) ? pdh : null, pdl: isFinite(pdl) ? pdl : null, mo };
}
const KZ = [[120, 300, 'London', 'rgba(76,141,255,.07)'], [510, 660, 'NY AM', 'rgba(34,195,142,.07)'], [810, 960, 'NY PM', 'rgba(245,165,36,.06)']];
const FIB = [[0, '0'], [0.5, '0.5'], [0.62, '0.62'], [0.705, '0.705'], [0.79, '0.79'], [1, '1'], [-0.27, '-0.27'], [-0.62, '-0.62']];
const DCOL = { h: '#f5a524', t: '#4c8dff', r: '#a78bfa', f: '#8fa3c7', m: '#4c8dff' };

function drawOv() {
  requestAnimationFrame(drawOv);
  const r = chartEl.getBoundingClientRect(), d = window.devicePixelRatio || 1;
  const W = Math.round(r.width * d), H = Math.round(r.height * d);
  if (ov.width !== W || ov.height !== H) { ov.width = W; ov.height = H; ov.style.width = r.width + 'px'; ov.style.height = r.height + 'px'; }
  og.setTransform(d, 0, 0, d, 0, 0); og.clearRect(0, 0, r.width, r.height);
  if (!D || !agg.length) return;
  const ts = chart.timeScale(), lr = ts.getVisibleLogicalRange(); if (!lr) return;
  const P = pane(), n = agg.length, from = Math.max(0, Math.floor(lr.from)), to = Math.min(n - 1, Math.ceil(lr.to));
  const X0 = j => ts.logicalToCoordinate(j), bs = Math.abs((X0(1) || 0) - (X0(0) || 0)) || 8;
  og.save(); og.beginPath(); og.rect(0, 0, P.w, P.h); og.clip(); og.font = '10px Inter, sans-serif'; og.textBaseline = 'middle';
  if (X.ict.kz && tf <= 3600) {
    let runZ = -1, runS = 0;
    for (let j = from; j <= to + 1; j++) {
      let z = -1; if (j <= to) { const m = todMin(agg[j].time); for (let k = 0; k < KZ.length; k++) if (m >= KZ[k][0] && m < KZ[k][1]) z = k; }
      if (z !== runZ) {
        if (runZ >= 0) { const x0 = X0(runS) - bs / 2, x1 = X0(j - 1) + bs / 2; og.fillStyle = KZ[runZ][3]; og.fillRect(x0, 0, x1 - x0, P.h); og.fillStyle = 'rgba(138,147,166,.75)'; og.fillText(KZ[runZ][2], x0 + 4, P.h - 9); }
        runZ = z; runS = j;
      }
    }
  }
  if (X.ict.fvg) {
    const gaps = [];
    for (let j = Math.min(n - 2, to); j >= Math.max(1, from) && gaps.length < 14; j--) {
      const a = agg[j - 1], c = agg[j + 1]; let lo, hi, bull;
      if (a.high < c.low) { lo = a.high; hi = c.low; bull = true; } else if (a.low > c.high) { lo = c.high; hi = a.low; bull = false; } else continue;
      if (hi - lo < TICK * 2) continue;
      let filled = false; for (let k = j + 2; k < n; k++) if (bull ? agg[k].low <= lo : agg[k].high >= hi) { filled = true; break; }
      if (!filled) gaps.push([j, lo, hi, bull]);
    }
    for (const [j, lo, hi, bull] of gaps) {
      const y0 = candle.priceToCoordinate(hi), y1 = candle.priceToCoordinate(lo); if (y0 == null || y1 == null) continue;
      const x0 = X0(j) - bs / 2;
      og.fillStyle = bull ? 'rgba(34,195,142,.13)' : 'rgba(240,81,106,.13)'; og.fillRect(x0, y0, P.w - x0, y1 - y0);
      og.strokeStyle = bull ? 'rgba(34,195,142,.45)' : 'rgba(240,81,106,.45)'; og.lineWidth = 1; og.setLineDash([3, 3]); const ym = (y0 + y1) / 2; og.beginPath(); og.moveTo(x0, ym); og.lineTo(P.w, ym); og.stroke(); og.setLineDash([]);
    }
  }
  if (X.ict.eq && n > 8) drawEq(P, from, to, n, X0);
  if (X.ict.lv || X.ict.rng || X.ict.pw || X.ict.orb) {
    const lv = calcLevels();
    if (lv) for (const [p, label, col] of lvList(lv)) {
      if (p == null) continue; const y = candle.priceToCoordinate(p); if (y == null) continue;
      og.strokeStyle = col; og.lineWidth = 1; og.setLineDash([2, 4]); og.beginPath(); og.moveTo(0, y); og.lineTo(P.w, y); og.stroke(); og.setLineDash([]);
      const tw = og.measureText(label).width; og.fillStyle = '#0b0d12'; og.fillRect(P.w - tw - 12, y - 8, tw + 8, 16); og.fillStyle = col; og.fillText(label, P.w - tw - 8, y);
    }
  }
  const all = X.pend && X.pend.b ? X.draws.concat([X.pend]) : X.draws;
  if (X.sigOn) drawSig(P);
  if (X.view) drawView(P);
  for (const s of all) drawShape(s, P, s.id != null && s.id === X.sel);
  og.restore();
}
function drawShape(s, P, sel) {
  const col = DCOL[s.type], A = ptXY(s.a), B = s.b ? ptXY(s.b) : null;
  og.lineWidth = sel ? 2 : 1.25; og.strokeStyle = col; og.fillStyle = col; og.setLineDash([]);
  const handle = q => { if (!sel || !q) return; og.fillStyle = '#0b0d12'; og.strokeStyle = col; og.lineWidth = 1.5; og.beginPath(); og.rect(q.x - 4, q.y - 4, 8, 8); og.fill(); og.stroke(); };
  if (s.type === 'h') {
    const y = candle.priceToCoordinate(s.a.p); if (y == null) return;
    og.beginPath(); og.moveTo(0, y); og.lineTo(P.w, y); og.stroke();
    const t = fx(s.a.p), tw = og.measureText(t).width; og.fillStyle = '#0b0d12'; og.fillRect(4, y - 16, tw + 8, 14); og.fillStyle = col; og.fillText(t, 8, y - 9);
    if (sel) handle({ x: P.w / 2, y }); return;
  }
  if (!A || !B) return;
  if (s.type === 't') { og.beginPath(); og.moveTo(A.x, A.y); og.lineTo(B.x, B.y); og.stroke(); }
  else if (s.type === 'r') { og.fillStyle = 'rgba(167,139,250,.14)'; og.fillRect(A.x, A.y, B.x - A.x, B.y - A.y); og.strokeRect(A.x, A.y, B.x - A.x, B.y - A.y); }
  else if (s.type === 'f') {
    const x0 = Math.min(A.x, B.x), x1 = Math.max(P.w, Math.max(A.x, B.x));
    og.setLineDash([4, 4]); og.beginPath(); og.moveTo(A.x, A.y); og.lineTo(B.x, B.y); og.stroke(); og.setLineDash([]);
    const yA = candle.priceToCoordinate(s.b.p + (s.a.p - s.b.p) * 0.62), yB = candle.priceToCoordinate(s.b.p + (s.a.p - s.b.p) * 0.79);
    if (yA != null && yB != null) { og.fillStyle = 'rgba(76,141,255,.10)'; og.fillRect(x0, Math.min(yA, yB), x1 - x0, Math.abs(yB - yA)); }
    for (const [lv, lab] of FIB) {
      const p = s.b.p + (s.a.p - s.b.p) * lv, y = candle.priceToCoordinate(p); if (y == null) continue;
      og.strokeStyle = lv === 0.705 ? '#f5a524' : lv < 0 ? '#22c38e' : col; og.lineWidth = lv === 0.705 ? 1.5 : 1; og.beginPath(); og.moveTo(x0, y); og.lineTo(x1, y); og.stroke();
      og.fillStyle = og.strokeStyle; og.fillText(`${lab}  ${fx(rt(p))}`, x0 + 4, y - 7);
    }
  } else if (s.type === 'm') {
    const up = s.b.p >= s.a.p; og.fillStyle = up ? 'rgba(34,195,142,.13)' : 'rgba(240,81,106,.13)'; og.strokeStyle = up ? '#22c38e' : '#f0516a';
    og.fillRect(A.x, A.y, B.x - A.x, B.y - A.y); og.strokeRect(A.x, A.y, B.x - A.x, B.y - A.y);
    const pts = s.b.p - s.a.p, bars = Math.round((s.b.t - s.a.t) / tf), q = Math.max(1, +$('#oQty').value || 1);
    const t = `${pts >= 0 ? '+' : ''}${fx(pts)} pts (${(pts / s.a.p * 100).toFixed(2)}%) · ${bars} bars · ${money(pts * S.pv * q)}`, tw = og.measureText(t).width;
    const cx = (A.x + B.x) / 2, cy = up ? Math.min(A.y, B.y) - 12 : Math.max(A.y, B.y) + 12;
    og.fillStyle = '#1b2130'; og.fillRect(cx - tw / 2 - 6, cy - 9, tw + 12, 18); og.fillStyle = '#d7dce5'; og.fillText(t, cx - tw / 2, cy);
  }
  handle(A); handle(B);
}

/* ---------- drawing interaction ---------- */
const wrapEl = $('#chartWrap');
const ptOf = e => { const r = chartEl.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
const inPane = q => { const P = pane(); return q.x >= 0 && q.y >= 0 && q.x <= P.w && q.y <= P.h; };
const dataPt = q => { const t = tOfX(q.x), p = candle.coordinateToPrice(q.y); return (t == null || p == null) ? null : { t, p: rt(p) }; };
const near = (q, a, r = 7) => a && Math.abs(q.x - a.x) <= r && Math.abs(q.y - a.y) <= r;
function segDist(q, a, b) { const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy || 1; let t = ((q.x - a.x) * dx + (q.y - a.y) * dy) / l2; t = Math.max(0, Math.min(1, t)); return Math.hypot(q.x - (a.x + t * dx), q.y - (a.y + t * dy)); }
function hitShape(q) { return hitPass(q, true) || hitPass(q, false); }
function hitPass(q, lines) {
  for (let i = X.draws.length - 1; i >= 0; i--) {
    const s = X.draws[i]; if ((s.type === 'h' || s.type === 't') !== lines) continue;
    if (s.type === 'h') { const y = candle.priceToCoordinate(s.a.p); if (y != null && Math.abs(y - q.y) < 6) return { s, mode: 'move' }; continue; }
    const A = ptXY(s.a), B = ptXY(s.b); if (!A || !B) continue;
    if (near(q, A)) return { s, mode: 'a' }; if (near(q, B)) return { s, mode: 'b' };
    if (s.type === 't') { if (segDist(q, A, B) < 6) return { s, mode: 'move' }; }
    else { const x0 = Math.min(A.x, B.x), x1 = Math.max(A.x, B.x), y0 = Math.min(A.y, B.y), y1 = Math.max(A.y, B.y); if (q.x >= x0 - 4 && q.x <= x1 + 4 && q.y >= y0 - 4 && q.y <= y1 + 4) return { s, mode: 'move' }; }
  }
  return null;
}
function setTool(t) { X.tool = t; X.pend = null; document.querySelectorAll('#tools [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t)); chartEl.classList.toggle('picking', t !== 'cursor' || pickMode); }
function delSel() { if (X.sel == null) return; X.draws = X.draws.filter(s => s.id !== X.sel); X.sel = null; scheduleSave(); }
wrapEl.addEventListener('pointerdown', e => {
  if (e.button !== 0 || pickMode || !chartEl.contains(e.target) || !D) return;
  const q = ptOf(e); if (!inPane(q)) return;
  if (X.tool !== 'cursor') {
    const p = dataPt(q); if (!p) return;
    if (X.tool === 'h') { X.draws.push({ id: X.nid++, type: 'h', a: p }); setTool('cursor'); scheduleSave(); }
    else if (!X.pend) X.pend = { type: X.tool, a: p, b: p };
    else { X.draws.push({ id: X.nid++, type: X.pend.type, a: X.pend.a, b: p }); X.sel = X.nid - 1; setTool('cursor'); scheduleSave(); }
  } else {
    if (hit(q.y)) return;                       // SL / TP / order line takes priority
    const h = hitShape(q);
    if (!h) { X.sel = null; return; }
    X.sel = h.s.id; const p0 = dataPt(q); if (!p0) return;
    X.drag = { s: h.s, mode: h.mode, p0, a0: { ...h.s.a }, b0: h.s.b ? { ...h.s.b } : null };
    chart.applyOptions({ handleScroll: false, handleScale: false });
  }
  X.busy = true; try { wrapEl.setPointerCapture(e.pointerId); } catch (_) {}
  e.preventDefault(); e.stopPropagation();
}, true);
['mousedown', 'touchstart'].forEach(ev => wrapEl.addEventListener(ev, e => { if (X.busy || (X.tool !== 'cursor' && chartEl.contains(e.target))) e.stopPropagation(); }, true));
wrapEl.addEventListener('pointermove', e => {
  if (!D) return; const q = ptOf(e);
  if (X.pend) { const p = dataPt(q); if (p) X.pend.b = p; }
  if (X.drag) {
    const p = dataPt(q); if (!p) return; const g = X.drag, dt = p.t - g.p0.t, dp = p.p - g.p0.p;
    if (g.mode === 'a') g.s.a = p; else if (g.mode === 'b') g.s.b = p;
    else { g.s.a = { t: g.a0.t + dt, p: rt(g.a0.p + dp) }; if (g.b0) g.s.b = { t: g.b0.t + dt, p: rt(g.b0.p + dp) }; }
    e.stopPropagation();
  }
}, true);
const endDraw = () => { if (X.drag) { X.drag = null; chart.applyOptions({ handleScroll: true, handleScale: true }); scheduleSave(); } X.busy = false; };
wrapEl.addEventListener('pointerup', endDraw, true); wrapEl.addEventListener('pointercancel', endDraw, true);
$('#tools').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.tool) setTool(b.dataset.tool);
  else if (b.id === 'tDel') { if (X.sel == null) toast('Click a drawing first, then delete it'); delSel(); }
  else if (b.id === 'tClear' && X.draws.length) modal('Clear drawings', '<p>Remove every drawing from the chart?</p>', [['Cancel'], ['Clear all', () => { X.draws = []; X.sel = null; scheduleSave(); }, 'primary']]);
});
document.addEventListener('keydown', e => {
  if (e.target.closest('input,select,textarea') || $('#modal').classList.contains('on') || e.metaKey || e.ctrlKey) return;
  const k = e.key.toLowerCase();
  if (e.key === 'Escape') setTool('cursor');
  else if (e.key === 'Delete' || e.key === 'Backspace') { if (X.sel != null) { e.preventDefault(); delSel(); } }
  else if (k === 'h') setTool('h'); else if (k === 't') setTool('t'); else if (k === 'r') setTool('r'); else if (k === 'g') setTool('f'); else if (k === 'm') setTool('m');
});

/* ---------- setup tag ---------- */
$('#oSetup').innerHTML = '<option value="">No setup tag</option>' + MODELS.map(m => `<option>${m}</option>`).join('');
$('#oSetup').onchange = e => { X.setup = e.target.value; scheduleSave(); };

/* ---------- ICT overlays ---------- */
$('#bICT').onclick = () => {
  const c = (k, l, h) => `<label class="chk" style="flex-direction:row;align-items:flex-start;gap:8px;margin-bottom:10px"><input type="checkbox" data-i="${k}" ${X.ict[k] ? 'checked' : ''}><span><b>${l}</b><br><span class="hint">${h}</span></span></label>`;
  modal('ICT overlays', c('kz', 'Kill zones', 'Shades London 02:00–05:00, New York AM 08:30–11:00 and New York PM 13:30–16:00 (New York time) on the 1-hour chart and below.') +
    c('lv', 'Key levels', 'Previous day high and low, using the 18:00 session roll, and the midnight opening price.') +
    c('fvg', 'Fair value gaps', 'Marks the most recent three-candle gaps in view that price has not fully filled yet, with the midpoint as a dashed line. A gap disappears once it is filled.') +
    c('rng', 'Asia and London ranges', 'High and low of the 20:00 to 24:00 Asia range and the 02:00 to 05:00 London range, using only bars that have already played.') +
    c('pw', 'Previous week high and low', 'The full range of the previous trading week.') +
    c('orb', 'Opening range', 'High and low of 09:30 to 09:45, shown once that window has started.') +
    c('eq', 'Equal highs and lows', 'Marks pairs of swing highs or lows within a few points of each other that price has not run through yet, the liquidity pools.'),
    [['Cancel'], ['Apply', () => { document.querySelectorAll('#mBody [data-i]').forEach(i => { X.ict[i.dataset.i] = i.checked; }); scheduleSave(); }, 'primary']]);
};

/* ---------- skip to time ---------- */
$('#skipSel').onchange = e => {
  const v = e.target.value; e.target.value = ''; if (!v || !D) return;
  if (D.baseSec >= 3600) { toast('Skip-to needs intraday data', 'var(--warn)'); return; }
  let idx = -1;
  if (v === 'day') { const k = Math.floor((D.dt[cur] + 21600) / 86400); for (let i = cur + 1; i < D.n; i++) if (Math.floor((D.dt[i] + 21600) / 86400) !== k) { idx = i; break; } }
  else { const tm = +v; for (let i = cur + 1; i < D.n; i++) { const a = todMin(D.dt[i - 1]), b = todMin(D.dt[i]); if (b === tm || (a < tm && b > tm) || (b < a && (tm > a || tm <= b))) { idx = i; break; } } }
  if (idx < 0) { toast('No later bar at that time in this data'); return; }
  jumpTo(idx);
};

/* ---------- screenshot ---------- */
$('#bShot').onclick = () => {
  try {
    const c = chart.takeScreenshot(), g = c.getContext('2d'); g.drawImage(ov, 0, 0, c.width, c.height);
    g.fillStyle = '#8a93a6'; g.font = `${11 * (window.devicePixelRatio || 1)}px Inter, sans-serif`; g.fillText(`${SYM()}1! · ${TFS.find(x => x[0] === tf)[1]} · ${fmtET(D.dt[cur], true, true)} ET`, 10 * (window.devicePixelRatio || 1), c.height - 34 * (window.devicePixelRatio || 1));
    const url = c.toDataURL('image/png');
    modal('Chart image', `<p class="hint" style="margin:0 0 10px">Use the button to download, or right-click the image to copy or save it.</p><img src="${url}" alt="Chart" style="width:100%;border-radius:8px;border:1px solid var(--line2)">`,
      [['Close'], ['Download PNG', () => { const a = document.createElement('a'); a.href = url; a.download = `${SYM()}-replay-${fmtET(D.dt[cur], false, true).replace(/[: ]/g, '-')}.png`; document.body.appendChild(a); a.click(); a.remove(); return false; }, 'primary']]);
  } catch (err) { toast('Could not capture the chart', 'var(--warn)'); }
};

/* ---------- prop challenge ---------- */
const PRESETS = { '50': [50000, 3000, 2000], '100': [100000, 6000, 3000], '150': [150000, 9000, 4500] };
function chCalc() {
  const a = acct(), start = S.balance; if (!X.ch.peak) X.ch.peak = start; if (a.eq > X.ch.peak) X.ch.peak = a.eq;
  const floor = S.chType === 'trailing' ? Math.min(start, X.ch.peak - S.chMaxDD) : start - S.chMaxDD;
  const days = new Set(closed.map(c => Math.floor((toET(c.entryT) + 21600) / 86400))).size;
  return { a, floor, room: a.eq - floor, dayRoom: S.chDaily ? S.chDaily + a.day : null, days };
}
function chFail(reason) {
  X.ch.state = 'failed'; X.ch.reason = reason;
  for (const tr of trades.slice()) closeTrade(tr, rt(lastPx() - tr.side * slip()), D.t[cur], 'Challenge breach');
  orders = []; dirty.ord = dirty.lines = true; pause();
  modal('Challenge failed', `<p><b>${esc(reason)}.</b> Open positions were closed and new orders are blocked.</p><p class="hint">Review the trades in History and Analytics, then start a new session to try again.</p>`, [['Review trades']]);
}
function chBar(i) {
  if (!S.chOn || X.ch.state !== 'active') return false;
  const realized = closed.reduce((s, c) => s + c.pnl, 0);
  const worstOpen = trades.reduce((s, t) => s + ((t.side > 0 ? D.l[i] : D.h[i]) - t.entry) * t.side * t.qty * S.pv, 0);
  const start = S.balance, floor = S.chType === 'trailing' ? Math.min(start, (X.ch.peak || start) - S.chMaxDD) : start - S.chMaxDD;
  if (start + realized + worstOpen <= floor) { chFail('Maximum drawdown reached'); return true; }
  if (S.chDaily) { const sk = Math.floor((D.dt[i] + 21600) / 86400); const day = closed.filter(c => Math.floor((toET(c.exitT) + 21600) / 86400) === sk).reduce((s, c) => s + c.pnl, 0) + worstOpen; if (day <= -S.chDaily) { chFail('Daily loss limit reached'); return true; } }
  const eq = start + realized + trades.reduce((s, t) => s + (D.c[i] - t.entry) * t.side * t.qty * S.pv, 0); if (eq > X.ch.peak) X.ch.peak = eq;
  return false;
}
function renderChallenge() {
  const card = $('#chCard'); card.style.display = S.chOn ? '' : 'none'; if (!S.chOn || !D) return;
  const c = chCalc();
  if (X.ch.state === 'active' && c.a.realized >= S.chTarget && !trades.length && c.days >= S.chMinDays) { X.ch.state = 'passed'; toast('Challenge passed', 'var(--up)'); scheduleSave(); }
  const st = X.ch.state, pr = Math.max(0, Math.min(1, c.a.realized / S.chTarget));
  $('#chState').innerHTML = st === 'passed' ? '<span class="up">PASSED</span>' : st === 'failed' ? '<span class="dn">FAILED</span>' : '<span class="mut">ACTIVE</span>';
  $('#chFill').style.width = (pr * 100).toFixed(1) + '%'; $('#chFill').style.background = st === 'failed' ? 'var(--dn)' : 'var(--up)';
  $('#chKv').innerHTML = `<span class="k">Profit target</span><span class="v">${money(Math.max(0, c.a.realized), false)} / ${money(S.chTarget, false)}</span>
    <span class="k">${S.chType === 'trailing' ? 'Trailing' : 'Static'} drawdown floor</span><span class="v">${money(c.floor, false)}</span>
    <span class="k">Room to floor</span><span class="v ${c.room < S.chMaxDD * .25 ? 'dn' : ''}">${money(Math.max(0, c.room), false)}</span>
    ${S.chDaily ? `<span class="k">Daily loss room</span><span class="v ${c.dayRoom < S.chDaily * .25 ? 'dn' : ''}">${money(Math.max(0, c.dayRoom), false)}</span>` : ''}
    <span class="k">Days traded</span><span class="v">${c.days}${S.chMinDays ? ' / ' + S.chMinDays : ''}</span>
    ${st === 'failed' ? `<span class="k dn" style="grid-column:1/-1">${esc(X.ch.reason)}</span>` : ''}`;
}
$('#bChal').onclick = () => {
  const f = (k, l, extra = '') => `<label>${l}<input class="inp" data-c="${k}" type="number" value="${S[k]}" ${extra}></label>`;
  modal('Prop firm challenge', `<div class="form">
    <label class="chk full" style="flex-direction:row"><input type="checkbox" data-c="chOn" ${S.chOn ? 'checked' : ''}>Run this session as a challenge</label>
    <label class="full">Preset<select class="inp" id="chPre"><option value="">Custom</option><option value="50">50K account · $3,000 target · $2,000 drawdown</option><option value="100">100K account · $6,000 target · $3,000 drawdown</option><option value="150">150K account · $9,000 target · $4,500 drawdown</option></select></label>
    <label>Account size ($)<input class="inp" data-c="balance" type="number" step="1000" value="${S.balance}"></label>
    ${f('chTarget', 'Profit target ($)', 'step="100"')}${f('chMaxDD', 'Maximum drawdown ($)', 'step="100"')}
    <label>Drawdown type<select class="inp" data-c="chType"><option value="trailing" ${S.chType === 'trailing' ? 'selected' : ''}>Trailing, locks at starting balance</option><option value="static" ${S.chType === 'static' ? 'selected' : ''}>Static</option></select></label>
    ${f('chDaily', 'Daily loss limit ($, 0 = none)', 'step="100" min="0"')}${f('chMinDays', 'Minimum trading days', 'step="1" min="0"')}
    <p class="hint full">Presets are typical futures evaluation numbers, not any firm's exact rules. Enter your own firm's figures. The trailing floor follows your highest equity, checked on each bar's close, and breaches are checked against each bar's worst price. Saving starts a fresh session at the current bar.</p></div>`,
    [['Cancel'], ['Save and start', () => {
      document.querySelectorAll('#mBody [data-c]').forEach(i => { const k = i.dataset.c; S[k] = i.type === 'checkbox' ? i.checked : (i.tagName === 'SELECT' ? i.value : Math.max(0, +i.value || 0)); });
      if (S.balance < 1000) S.balance = 50000; if (S.chMaxDD <= 0) S.chMaxDD = 2000; if (S.chTarget <= 0) S.chTarget = 3000;
      pause(); resetSession(); rebuild(true); scheduleSave(); toast(S.chOn ? 'Challenge started' : 'Challenge mode off');
    }, 'primary']]);
  $('#chPre').onchange = e => { const p = PRESETS[e.target.value]; if (!p) return; const set = (k, v) => { document.querySelector(`#mBody [data-c="${k}"]`).value = v; }; set('balance', p[0]); set('chTarget', p[1]); set('chMaxDD', p[2]); document.querySelector('#mBody [data-c="chOn"]').checked = true; };
};

/* ---------- analytics ---------- */
function grp(keyFn, order) {
  const m = new Map(); for (const c of closed) { const k = keyFn(c); if (!m.has(k)) m.set(k, []); m.get(k).push(c); }
  const rows = [...m.entries()].map(([k, a]) => { const w = a.filter(c => c.pnl > 0), gp = w.reduce((s, c) => s + c.pnl, 0), net = a.reduce((s, c) => s + c.pnl, 0), gl = gp - net, rs = a.filter(c => c.r != null);
    return { k, n: a.length, wr: w.length / a.length * 100, net, exp: net / a.length, pf: gl > 0 ? gp / gl : (gp ? Infinity : 0), avgR: rs.length ? rs.reduce((s, c) => s + c.r, 0) / rs.length : null }; });
  if (order) rows.sort((a, b) => order.indexOf(a.k) - order.indexOf(b.k)); else rows.sort((a, b) => b.net - a.net);
  return rows;
}
function anTable(title, rows) {
  const mx = Math.max(1, ...rows.map(r => Math.abs(r.net)));
  return `<div class="an"><h4>${title}</h4><table><tr><th></th><th>Trades</th><th>Win %</th><th>Net</th><th>Avg R</th><th>PF</th><th style="width:26%"></th></tr>${rows.map(r => `<tr><td class="txt">${esc(r.k)}</td><td>${r.n}</td><td>${r.wr.toFixed(0)}%</td><td class="${cls(r.net)}">${money(r.net)}</td><td class="${cls(r.avgR)}">${r.avgR == null ? '—' : r.avgR.toFixed(2) + 'R'}</td><td>${r.pf === Infinity ? '∞' : r.pf.toFixed(2)}</td><td><i class="anbar ${r.net >= 0 ? 'u' : 'd'}" style="width:${(Math.abs(r.net) / mx * 100).toFixed(0)}%"></i></td></tr>`).join('')}</table></div>`;
}
function renderAnalytics() {
  const el = $('#anaPane'); X.an = closed.length;
  if (!closed.length) { el.innerHTML = '<div class="empty">Close a few trades and this tab breaks your results down by setup, session, weekday and time of day.</div>'; return; }
  const wd = c => DOW[new Date(toET(c.entryT) * 1000).getUTCDay()], hr = c => String(new Date(toET(c.entryT) * 1000).getUTCHours()).padStart(2, '0') + ':00';
  const bySetup = grp(c => c.model || 'Untagged'), bySess = grp(c => c.sess || sessOf(c.entryT), ['Asia', 'London', 'NY AM', 'NY PM', 'Other']), byDay = grp(wd, DOW), byHr = grp(hr); byHr.sort((a, b) => a.k < b.k ? -1 : 1);
  const seg = [...bySetup.map(r => ['setup', r]), ...bySess.map(r => ['session', r]), ...byDay.map(r => ['day', r]), ...byHr.map(r => ['hour', r])].filter(x => x[1].n >= 5 && x[1].k !== 'Untagged');
  let ins = '';
  if (seg.length >= 2) { const s2 = seg.slice().sort((a, b) => b[1].exp - a[1].exp), b = s2[0], w = s2[s2.length - 1];
    ins = `<div class="anins"><span>Strongest: <b>${esc(b[1].k)}</b> (${b[0]}), ${money(b[1].exp)} per trade over ${b[1].n} trades</span><span>Weakest: <b>${esc(w[1].k)}</b> (${w[0]}), ${money(w[1].exp)} per trade over ${w[1].n} trades</span></div>`; }
  else ins = '<div class="anins"><span>Strongest and weakest segments appear once a setup, session, day or hour has at least 5 trades.</span></div>';
  const rb = [['≤ −1R', r => r <= -1], ['−1R to 0', r => r > -1 && r <= 0], ['0 to 1R', r => r > 0 && r <= 1], ['1R to 2R', r => r > 1 && r <= 2], ['2R to 3R', r => r > 2 && r <= 3], ['> 3R', r => r > 3]];
  const rs = closed.filter(c => c.r != null), rc = rb.map(([l, f]) => [l, rs.filter(c => f(c.r)).length]), rmx = Math.max(1, ...rc.map(x => x[1]));
  const days = new Map(); for (const c of closed) { const k = fmtET(toET(c.exitT), false, true).slice(0, 10); days.set(k, (days.get(k) || 0) + c.pnl); }
  const dl = [...days.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1).slice(-30), dmx = Math.max(1, ...dl.map(x => Math.abs(x[1])));
  el.innerHTML = `<div class="anwrap">${ins}${insightsHtml()}<div class="angrid">${anTable('By setup', bySetup)}${anTable('By session', bySess)}${anTable('By weekday', byDay)}${anTable('By entry hour (ET)', byHr)}${anTable('By side', grp(c => c.side > 0 ? 'Long' : 'Short'))}${anTable('By exit', grp(c => c.reason))}${anTable('By checklist', grp(c => c.rules === 'followed' ? 'Followed checklist' : c.rules === 'skipped' ? 'Skipped checklist' : 'No checklist'))}${anTable('By re-entry', grp(c => c.rev ? 'Bigger size right after a loss' : 'Normal entry'))}${anTable('By grade', grp(c => c.grade || 'Ungraded', ['A', 'B', 'C', 'Ungraded']))}
    ${calHtml()}<div class="an"><h4>R-multiple distribution</h4><div class="rdist">${rc.map(([l, n], i) => `<div><i class="${i < 2 ? 'd' : 'u'}" style="height:${(n / rmx * 100).toFixed(0)}%"></i><b>${n}</b><span>${l}</span></div>`).join('')}</div>${rs.length < closed.length ? `<div class="hint">${closed.length - rs.length} trade(s) had no stop, so no R value.</div>` : ''}</div>
    <div class="an"><h4>Daily P&amp;L${dl.length === 30 ? ' (last 30 days)' : ''}</h4><div class="dayp">${dl.map(([k, v]) => `<div title="${k} ${money(v)}"><i class="${v >= 0 ? 'u' : 'd'}" style="height:${(Math.abs(v) / dmx * 100).toFixed(0)}%"></i></div>`).join('')}</div><div class="hint">${dl.filter(x => x[1] > 0).length} green · ${dl.filter(x => x[1] <= 0).length} red days</div></div></div></div>`;
}

/* ---------- saved sessions ---------- */
const LSS = 'mnqreplay.sessions';
const sessList = () => { try { return JSON.parse(localStorage.getItem(LSS) || '[]') || []; } catch (_) { return []; } };
function snap(name) { return { id: Date.now(), name, saved: Date.now(), ds: D.name + '|' + D.n, dsName: D.name, kind: D.kind, curT: D.t[cur], tf, trades, orders, closed, nextId, S: { ...S }, X: X.dump() }; }
function openSessions() {
  const L = sessList(), net = closed.reduce((s, c) => s + c.pnl, 0);
  modal('Sessions', `<div class="row"><input class="inp" id="ssName" placeholder="Name this session, e.g. Silver Bullet · August" style="flex:1" maxlength="60"><button class="btn primary" id="ssSave">Save current</button></div>
    <p class="hint" style="margin:0 0 12px">Current session: ${closed.length} closed trade(s), ${money(net)} net, on ${esc(D.name)}. The current session also autosaves.</p>
    ${L.length ? `<table><tr><th>Name</th><th>Trades</th><th>Net</th><th>Dataset</th><th></th></tr>${L.map(s => { const n = (s.closed || []).reduce((a, c) => a + c.pnl, 0); return `<tr data-id="${s.id}"><td class="txt">${esc(s.name)}</td><td>${(s.closed || []).length}</td><td class="${cls(n)}">${money(n)}</td><td class="txt mut" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${esc(s.dsName || '')}</td><td><button class="xs" data-a="load">Load</button><button class="xs" data-a="del">Delete</button></td></tr>`; }).join('')}</table>` : '<div class="empty" style="padding:16px">No saved sessions yet.</div>'}`, [['Close']]);
  $('#ssSave').onclick = () => { const name = $('#ssName').value.trim() || `Session ${fmtET(D.dt[cur], false, true)}`; const L2 = sessList(); L2.unshift(snap(name)); try { localStorage.setItem(LSS, JSON.stringify(L2.slice(0, 25))); toast('Session saved'); } catch (_) { toast('Could not save: browser storage is full', 'var(--warn)'); } openSessions(); };
  $('#mBody').onclick = e => {
    const b = e.target.closest('button[data-a]'); if (!b) return; const id = +b.closest('tr').dataset.id, L3 = sessList(), s = L3.find(x => x.id === id); if (!s) return;
    if (b.dataset.a === 'del') { localStorage.setItem(LSS, JSON.stringify(L3.filter(x => x.id !== id))); openSessions(); return; }
    const go = ds => { if (s.S) S = { ...DEF, ...s.S }; useDataset(ds, s); $('#ctrLbl').textContent = ctrName(); closeModal(); scheduleSave(); toast(`Loaded "${s.name}"`); };
    if (s.ds === D.name + '|' + D.n) go(D); else libGet(s.ds).then(ds => ds ? (idbPut(ds), go(ds)) : toast(`Load the dataset "${s.dsName}" first (Data button), then load this session`, 'var(--warn)'));
  };
}
$('#bSess').onclick = openSessions;
requestAnimationFrame(drawOv);

$('#bExp').onclick = () => { const on = $('#app').classList.toggle('exp'); $('#bExp').textContent = on ? 'Shrink panel' : 'Expand panel'; if ($('#statsPane').classList.contains('on')) drawEquity(); };
