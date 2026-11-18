/* ============================== v7: strategy builder ============================== */
X.sig = []; X.sigOn = false;
const SKEY = 'mnqreplay.strats', SCUR = 'mnqreplay.stratcur';
const LV = [['pd', 'Prior session high / low'], ['asia', 'Asia range high / low'], ['lon', 'London range high / low'], ['or', 'Opening range (09:30-09:45) high / low'], ['mid', 'Midnight open']];
const CS = {
  time: { l: 'Time window (ET)', f: [['a', 'time', 'from'], ['b', 'time', 'to']], d: { a: '09:30', b: '11:00' } },
  kz: { l: 'Inside a kill zone', f: [], d: {} },
  trend: { l: 'Trend agrees: close and fast EMA beyond slow EMA', f: [['f', 'num', 'fast'], ['s', 'num', 'slow']], d: { f: 9, s: 21 } },
  vwap: { l: 'Close on the trade side of VWAP', f: [], d: {} },
  disp: { l: 'Displacement candle: large body, closes near its extreme', f: [['k', 'num', 'x avg body']], d: { k: 1.5 } },
  fvg: { l: 'Fair value gap formed in the last few bars', f: [['n', 'num', 'bars']], d: { n: 3 } },
  sweep: { l: 'Swept a recent extreme, then closed back inside', f: [['n', 'num', 'lookback'], ['w', 'num', 'within bars']], d: { n: 20, w: 3 } },
  brk: { l: 'Closed beyond the prior N-bar extreme', f: [['n', 'num', 'bars']], d: { n: 20 } },
  lvl: { l: 'Closed across a session level', f: [['lv', 'sel', 'level', LV]], d: { lv: 'pd' } },
  eng: { l: 'Engulfing candle', f: [], d: {} },
  pull: { l: 'Pulled back to the fast EMA, closed back away', f: [['f', 'num', 'EMA'], ['n', 'num', 'within bars']], d: { f: 9, n: 3 } }
};
const STPRE = {
  'Blank': { conds: [] },
  'Sweep + displacement in a kill zone': { conds: [{ t: 'kz' }, { t: 'sweep', n: 20, w: 3 }, { t: 'disp', k: 1.5 }], stop: { t: 'pts', v: 20 }, tgt: { t: 'r', v: 2 }, tf: 300 },
  'Opening range break': { conds: [{ t: 'time', a: '09:45', b: '11:30' }, { t: 'lvl', lv: 'or' }, { t: 'vwap' }], stop: { t: 'swing', v: 0 }, tgt: { t: 'r', v: 2 }, tf: 300 },
  'Trend pullback after a gap': { conds: [{ t: 'trend', f: 9, s: 21 }, { t: 'fvg', n: 5 }, { t: 'pull', f: 9, n: 3 }], stop: { t: 'atr', v: 1.5 }, tgt: { t: 'r', v: 2 }, tf: 300 }
};
const sdef = () => ({ name: 'My rules', dir: 'long', tf: 300, conds: [{ t: 'kz' }, { t: 'sweep', n: 20, w: 3 }, { t: 'disp', k: 1.5 }], stop: { t: 'pts', v: 20 }, tgt: { t: 'r', v: 2 }, exitAt: '15:55', be: 0, maxHold: 0, qty: 1, riskOn: false, risk: 100, maxDay: 3, dayLoss: 0, range: 'all' });
let ST = (() => { try { return Object.assign(sdef(), JSON.parse(localStorage.getItem(SCUR) || '{}')); } catch (e) { return sdef(); } })();
let SRES = null;
const hmMin = s => { const m = /^(\d{1,2}):(\d{2})$/.exec(s || ''); return m ? (+m[1]) * 60 + (+m[2]) : -1; };
const stSave = () => { try { localStorage.setItem(SCUR, JSON.stringify(ST)); } catch (e) { } };
const stList = () => { try { return JSON.parse(localStorage.getItem(SKEY) || '[]'); } catch (e) { return []; } };

/* ---------- engine ---------- */
function sBars(tf) {
  const B = []; let key = null, b = null, vk = null, pv = 0, vv = 0;
  for (let i = 0; i < D.n; i++) {
    const dt = D.dt[i], k = tf >= 86400 ? Math.floor((dt + 21600) / 86400) : Math.floor(dt / tf), sk = Math.floor((dt + 21600) / 86400);
    if (sk !== vk) { vk = sk; pv = 0; vv = 0; }
    const w = D.v[i] > 0 ? D.v[i] : 1; pv += (D.h[i] + D.l[i] + D.c[i]) / 3 * w; vv += w;
    if (k !== key) { key = k; b = { dt, o: D.o[i], h: D.h[i], l: D.l[i], c: D.c[i], i0: i, i1: i, vw: 0 }; B.push(b); }
    else { if (D.h[i] > b.h) b.h = D.h[i]; if (D.l[i] < b.l) b.l = D.l[i]; b.c = D.c[i]; b.i1 = i; }
    b.vw = pv / vv;
  }
  return B;
}
function sInd(B) {
  const cache = {}, ema = n => { n = Math.max(1, Math.round(n)); if (cache[n]) return cache[n]; const a = new Float64Array(B.length), kf = 2 / (n + 1); for (let j = 0; j < B.length; j++) a[j] = j ? a[j - 1] + kf * (B[j].c - a[j - 1]) : B[j].c; return cache[n] = a; };
  const ab = new Float64Array(B.length), atr = new Float64Array(B.length); let sb = 0, st = 0;
  for (let j = 0; j < B.length; j++) {
    const bd = Math.abs(B[j].c - B[j].o), tr = j ? Math.max(B[j].h - B[j].l, Math.abs(B[j].h - B[j - 1].c), Math.abs(B[j].l - B[j - 1].c)) : B[j].h - B[j].l;
    ab[j] = j >= 5 ? sb / Math.min(j, 20) : 0; sb += bd; if (j >= 20) sb -= Math.abs(B[j - 20].c - B[j - 20].o);
    st += tr; if (j >= 14) st -= (B[j - 14].tr || 0); B[j].tr = tr; atr[j] = j >= 14 ? st / 14 : 0;
  }
  const L = new Array(B.length); let sk = null, S0 = null, prev = null;
  for (let j = 0; j < B.length; j++) {
    const b = B[j], k = Math.floor((b.dt + 21600) / 86400), m = todMin(b.dt);
    if (k !== sk) { prev = S0; sk = k; S0 = { hi: -Infinity, lo: Infinity, ah: null, al: null, lh: null, ll: null, oh: null, ol: null, mid: null }; }
    if (b.h > S0.hi) S0.hi = b.h; if (b.l < S0.lo) S0.lo = b.l;
    if (m >= 1200) { S0.ah = Math.max(S0.ah ?? -Infinity, b.h); S0.al = Math.min(S0.al ?? Infinity, b.l); }
    if (m >= 120 && m < 300) { S0.lh = Math.max(S0.lh ?? -Infinity, b.h); S0.ll = Math.min(S0.ll ?? Infinity, b.l); }
    if (m >= 570 && m < 585) { S0.oh = Math.max(S0.oh ?? -Infinity, b.h); S0.ol = Math.min(S0.ol ?? Infinity, b.l); }
    if (m === 0) S0.mid = b.o;
    const post = m < 1080;
    L[j] = { pdh: prev ? prev.hi : null, pdl: prev ? prev.lo : null, ash: post ? S0.ah : null, asl: post ? S0.al : null, lonh: post && m >= 300 ? S0.lh : null, lonl: post && m >= 300 ? S0.ll : null, orh: post && m >= 585 ? S0.oh : null, orl: post && m >= 585 ? S0.ol : null, mid: post ? S0.mid : null };
  }
  return { ema, ab, atr, L };
}
function sChk(c, j, d, B, I) {
  const b = B[j];
  switch (c.t) {
    case 'time': { const m = todMin(b.dt), a = hmMin(c.a), z = hmMin(c.b); return a <= z ? (m >= a && m < z) : (m >= a || m < z); }
    case 'kz': { const m = todMin(b.dt); return KZ.some(z => m >= z[0] && m < z[1]); }
    case 'trend': { const f = I.ema(c.f)[j], s = I.ema(c.s)[j]; return d > 0 ? (b.c > s && f > s) : (b.c < s && f < s); }
    case 'vwap': return d * (b.c - b.vw) > 0;
    case 'disp': { const ab = I.ab[j], rg = b.h - b.l; return ab > 0 && rg > 0 && (b.c - b.o) * d >= c.k * ab && (d > 0 ? (b.c - b.l) / rg : (b.h - b.c) / rg) >= 0.7; }
    case 'fvg': { const n = Math.max(1, c.n | 0); for (let m = j; m > j - n && m >= 2; m--) if (d > 0 ? B[m].l > B[m - 2].h : B[m].h < B[m - 2].l) return true; return false; }
    case 'sweep': { const n = Math.max(2, c.n | 0), w = Math.max(1, c.w | 0); for (let m = j; m > j - w && m >= n; m--) { let e = d > 0 ? Infinity : -Infinity; for (let q = m - n; q < m; q++) e = d > 0 ? Math.min(e, B[q].l) : Math.max(e, B[q].h); if (d > 0 ? (B[m].l < e && b.c > e) : (B[m].h > e && b.c < e)) return true; } return false; }
    case 'brk': { const n = Math.max(2, c.n | 0); if (j < n) return false; let e = d > 0 ? -Infinity : Infinity; for (let q = j - n; q < j; q++) e = d > 0 ? Math.max(e, B[q].h) : Math.min(e, B[q].l); return d > 0 ? b.c > e : b.c < e; }
    case 'lvl': { const l = I.L[j], p = { pd: [l.pdh, l.pdl], asia: [l.ash, l.asl], lon: [l.lonh, l.lonl], or: [l.orh, l.orl], mid: [l.mid, l.mid] }[c.lv]; const lv = p ? (d > 0 ? p[0] : p[1]) : null; if (lv == null || j < 1) return false; return d > 0 ? (b.c > lv && B[j - 1].c <= lv) : (b.c < lv && B[j - 1].c >= lv); }
    case 'eng': { const p = B[j - 1]; if (!p) return false; return d > 0 ? (p.c < p.o && b.c > b.o && b.c >= p.o && b.o <= p.c) : (p.c > p.o && b.c < b.o && b.c <= p.o && b.o >= p.c); }
    case 'pull': { const f = I.ema(c.f), n = Math.max(1, c.n | 0); let t = false; for (let m = j; m > j - n && m >= 0; m--) if (d > 0 ? B[m].l <= f[m] : B[m].h >= f[m]) { t = true; break; } return t && (d > 0 ? b.c > f[j] : b.c < f[j]); }
  }
  return false;
}
function sRange(st) {
  if (st.range === 'now') return [0, cur];
  if (/^s\d+$/.test(st.range)) { const N = +st.range.slice(1); let cnt = 0, last = null; for (let i = D.n - 1; i >= 0; i--) { const k = Math.floor((D.dt[i] + 21600) / 86400); if (k !== last) { last = k; cnt++; if (cnt > N) return [i + 1, D.n - 1]; } } return [0, D.n - 1]; }
  return [0, D.n - 1];
}
function sRun(st) {
  const tf = Math.max(D.baseSec, st.tf), B = sBars(tf), I = sInd(B), [r0, r1] = sRange(st), dirs = st.dir === 'both' ? [1, -1] : [st.dir === 'short' ? -1 : 1];
  const exitMin = hmMin(st.exitAt), pvv = S.pv, slip = S.slipTicks * TICK, sigs = [], out = [];
  let busy = -1, dayK = null, dayN = 0, dayPnl = 0;
  for (let j = 30; j < B.length - 1; j++) {
    const b = B[j], nb = B[j + 1]; if (b.i0 < r0 || nb.i0 > r1) continue;
    for (const d of dirs) {
      if (!st.conds.every(c => sChk(c, j, d, B, I))) continue;
      sigs.push({ i: b.i1, d });
      const e = nb.i0; if (e <= busy || (tf < 86400 && nb.dt - b.dt > 2 * tf)) continue;
      const dk = Math.floor(b.dt / 86400); if (dk !== dayK) { dayK = dk; dayN = 0; dayPnl = 0; }
      if (st.maxDay > 0 && dayN >= st.maxDay) continue; if (st.dayLoss > 0 && dayPnl <= -st.dayLoss) continue;
      const tm = todMin(nb.dt); if (exitMin >= 0 && tm >= exitMin && tm < 1080) continue;
      const entry = D.o[e] + d * slip; let dist;
      if (st.stop.t === 'atr') dist = st.stop.v * I.atr[j]; else if (st.stop.t === 'swing') { let x = d > 0 ? Infinity : -Infinity; for (let q = Math.max(0, j - 2); q <= j; q++) x = d > 0 ? Math.min(x, B[q].l) : Math.max(x, B[q].h); dist = (entry - x) * d + TICK; } else dist = st.stop.v;
      dist = Math.max(TICK, Math.round(dist / TICK) * TICK); if (!(dist > 0) || !isFinite(dist)) continue;
      const tg = st.tgt.t === 'r' ? st.tgt.v * dist : st.tgt.t === 'pts' ? st.tgt.v : 0;
      const qty = st.riskOn ? Math.min(50, Math.max(1, Math.floor(st.risk / (dist * pvv)))) : Math.max(1, st.qty | 0);
      let stop = entry - d * dist, tgt = tg > 0 ? entry + d * tg : null, xi = D.n - 1, xp = D.c[D.n - 1], why = 'End of data', moved = false;
      const hold = st.maxHold > 0 ? Math.round(st.maxHold * tf / D.baseSec) : 0;
      for (let m = e; m <= r1; m++) {
        if (m > e && D.dt[m] - D.dt[m - 1] > 7200) { xi = m - 1; xp = D.c[m - 1]; why = 'Session break'; break; }
        const tm2 = todMin(D.dt[m]);
        if (m > e && exitMin >= 0 && tm2 >= exitMin && tm2 < 1080) { xi = m; xp = D.o[m] - d * slip; why = 'Time exit'; break; }
        if (d > 0 ? D.l[m] <= stop : D.h[m] >= stop) { xi = m; xp = (m > e ? (d > 0 ? Math.min(stop, D.o[m]) : Math.max(stop, D.o[m])) : stop) - d * slip; why = moved ? 'Breakeven' : 'Stop'; break; }
        if (tgt != null && (d > 0 ? D.h[m] >= tgt : D.l[m] <= tgt)) { xi = m; xp = m > e ? (d > 0 ? Math.max(tgt, D.o[m]) : Math.min(tgt, D.o[m])) : tgt; why = 'Target'; break; }
        if (st.be > 0 && !moved && (d > 0 ? D.h[m] >= entry + st.be * dist : D.l[m] <= entry - st.be * dist)) { stop = entry; moved = true; }
        if (hold && m - e >= hold) { xi = m; xp = D.c[m] - d * slip; why = 'Max hold'; break; }
        if (m === r1) { xi = m; xp = D.c[m]; why = 'End of range'; }
      }
      const pts = (xp - entry) * d, gross = pts * qty * pvv, comm = commRT(qty), pnl = gross - comm;
      out.push({ d, qty, e, xi, entry, exit: xp, dist, pts, pnl, r: pnl / (dist * qty * pvv), why, stop0: entry - d * dist, tgt0: tgt });
      busy = xi; dayN++; dayPnl += pnl;
    }
  }
  return { trades: out, sigs, bars: B.length };
}
function sStats(tr) {
  const n = tr.length; if (!n) return null;
  const w = tr.filter(t => t.pnl > 0), l = tr.filter(t => t.pnl < 0), net = tr.reduce((s, t) => s + t.pnl, 0), gp = w.reduce((s, t) => s + t.pnl, 0), gl = -l.reduce((s, t) => s + t.pnl, 0);
  let eq = S.balance, pk = eq, dd = 0, ls = 0, mls = 0; const curve = [eq];
  for (const t of tr) { eq += t.pnl; curve.push(eq); pk = Math.max(pk, eq); dd = Math.max(dd, pk - eq); if (t.pnl < 0) { ls++; mls = Math.max(mls, ls); } else ls = 0; }
  const rs = tr.map(t => t.r); return { n, wr: w.length / n, net, pf: gl > 0 ? gp / gl : null, avgR: rs.reduce((a, b) => a + b, 0) / n, avgW: w.length ? gp / w.length : 0, avgL: l.length ? -gl / l.length : 0, dd, mls, curve, best: Math.max(...tr.map(t => t.pnl)), worst: Math.min(...tr.map(t => t.pnl)) };
}

/* ---------- chart: rule hits and a reviewed hypothetical trade ---------- */
function drawSig(P) {
  const a = X.sig; if (!a.length || !agg.length) return; let lo = 0, hi = a.length - 1, last = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m].i <= cur) { last = m; lo = m + 1; } else hi = m - 1; }
  og.setLineDash([]); let drawn = 0;
  for (let q = last; q >= 0 && drawn < 400; q--) {
    const s = a[q], x = xOfT(D.dt[s.i] - (D.dt[s.i] % Math.max(60, tf))); if (x == null) { if (drawn) break; else continue; } if (x < -10) break; if (x > P.w + 10) continue;
    const y = candle.priceToCoordinate(s.d > 0 ? D.l[s.i] : D.h[s.i]); if (y == null) continue; drawn++;
    const yy = s.d > 0 ? y + 12 : y - 12, k = s.d > 0 ? -1 : 1;
    og.fillStyle = 'rgba(122,162,255,.95)'; og.beginPath(); og.moveTo(x, yy + k * 6); og.lineTo(x - 5, yy - k * 5); og.lineTo(x + 5, yy - k * 5); og.closePath(); og.fill();
  }
}
function stView(t) {
  const c = { id: -1, side: t.d, qty: t.qty, entry: t.entry, entryT: D.t[t.e], exit: t.exit, exitT: D.t[t.xi], pnl: t.pnl, r: t.r, reason: t.why, initSL: t.stop0, tp: t.tgt0 };
  closeModal(); jumpTo(Math.min(D.n - 1, t.xi + Math.round(20 * Math.max(60, tf) / D.baseSec))); X.view = c;
  const a = idxOfT(toET(c.entryT)), b = idxOfT(toET(c.exitT));
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, a - 50), to: Math.min(agg.length + 10, b + 40) });
  banner(`Rule-tester trade · ${t.d > 0 ? 'long' : 'short'} ${t.qty} · ${money(t.pnl)} · press Esc or step the replay to clear`);
}

/* ---------- builder UI ---------- */
const sel = (k, opts, v, extra = '') => `<select class="inp" data-k="${k}" ${extra}>${opts.map(([a, b]) => `<option value="${a}" ${String(a) === String(v) ? 'selected' : ''}>${b}</option>`).join('')}</select>`;
const num = (k, v, w = 66, st = 'any') => `<input class="inp mono" type="number" data-k="${k}" value="${v}" step="${st}" style="width:${w}px">`;
function condRow(c, i) {
  const sp = CS[c.t];
  const f = sp.f.map(([k, ty, lb, op]) => ty === 'time' ? `<span class="hint">${lb}</span><input class="inp mono" data-k="c.${i}.${k}" value="${c[k]}" placeholder="09:30" style="width:64px">` : ty === 'sel' ? sel(`c.${i}.${k}`, op, c[k]) : `<span class="hint">${lb}</span>${num(`c.${i}.${k}`, c[k], 58)}`).join('');
  return `<div class="strow"><span class="hint" style="width:18px">${i + 1}</span>${sel(`c.${i}.t`, Object.entries(CS).map(([a, v]) => [a, v.l]), c.t, 'style="flex:1;min-width:200px"')}${f}<button class="xs" data-del="${i}" title="Remove this rule">Remove</button></div>`;
}
function stHtml() {
  const tfo = TFS.filter(([s]) => s >= D.baseSec && s % D.baseSec === 0 && s <= 14400), saved = stList();
  return `<div class="stb">
  <div class="strow"><span class="stl">Start from</span>${sel('preset', Object.keys(STPRE).map(k => [k, k]), '', 'id="stPre"')}
    <span class="stl" style="margin-left:10px">Saved</span><select class="inp" id="stSaved"><option value="">Saved rule sets (${saved.length})</option>${saved.map((s, i) => `<option value="${i}">${s.name.replace(/</g, '')}</option>`).join('')}</select>
    <button class="xs" id="stLoad">Load</button><button class="xs" id="stDelS">Delete</button></div>
  <div class="strow"><span class="stl">Name</span><input class="inp" data-k="name" value="${ST.name.replace(/"/g, '')}" style="width:190px"><button class="xs" id="stSaveBtn">Save rule set</button>
    <span class="stl" style="margin-left:10px">Direction</span>${sel('dir', [['long', 'Long side only'], ['short', 'Short side only'], ['both', 'Both sides (rules mirrored)']], ST.dir)}
    <span class="stl" style="margin-left:10px">Chart timeframe</span>${sel('tf', tfo.map(([s, l]) => [s, l]), ST.tf)}</div>
  <h4>All of these must be true on a closed bar</h4>
  ${ST.conds.map(condRow).join('') || '<div class="hint" style="padding:6px 0">No rules yet. Add one below.</div>'}
  <div class="strow"><button class="xs" id="stAdd">Add a rule</button><span class="hint">When every rule is met, the next bar's open is where the simulated trade starts.</span></div>
  <h4>Exits and risk</h4>
  <div class="strow"><span class="stl">Stop</span>${sel('stop.t', [['pts', 'Fixed points'], ['atr', 'x ATR(14)'], ['swing', 'Beyond last 3 bars']], ST.stop.t)}${ST.stop.t === 'swing' ? '' : num('stop.v', ST.stop.v, 62)}
    <span class="stl" style="margin-left:10px">Target</span>${sel('tgt.t', [['r', 'R multiple'], ['pts', 'Fixed points'], ['none', 'No target']], ST.tgt.t)}${ST.tgt.t === 'none' ? '' : num('tgt.v', ST.tgt.v, 62)}
    <span class="stl" style="margin-left:10px">Breakeven at</span>${num('be', ST.be, 56)}<span class="hint">R (0 = off)</span></div>
  <div class="strow"><span class="stl">Flat by</span><input class="inp mono" data-k="exitAt" value="${ST.exitAt}" placeholder="15:55" style="width:64px"><span class="hint">ET, blank = none</span>
    <span class="stl" style="margin-left:10px">Max hold</span>${num('maxHold', ST.maxHold, 56)}<span class="hint">bars (0 = off)</span>
    <span class="stl" style="margin-left:10px">Max per day</span>${num('maxDay', ST.maxDay, 50)}<span class="stl" style="margin-left:10px">Stop day after losing $</span>${num('dayLoss', ST.dayLoss, 62)}</div>
  <div class="strow"><span class="stl">Size</span>${sel('riskOn', [['0', 'Fixed contracts'], ['1', 'Risk $ per trade']], ST.riskOn ? '1' : '0')}${ST.riskOn ? num('risk', ST.risk, 70) : num('qty', ST.qty, 56)}
    <span class="stl" style="margin-left:10px">Test on</span>${sel('range', [['all', 'All loaded data'], ['s60', 'Last 60 sessions'], ['s20', 'Last 20 sessions'], ['now', 'Up to the replay position']], ST.range)}</div>
  <div class="hint" style="margin:8px 0">This runs your own rules on the data you loaded. Fills use the same costs as the replay (commission, slippage, conservative stop-first). It tests a hypothesis about the past. It does not predict anything, and the more you adjust rules to fit one dataset, the less the result means.</div>
  <div id="stRes"></div></div>`;
}
function stResHtml() {
  const r = SRES; if (!r) return '';
  const s = sStats(r.trades);
  if (!s) return `<div class="an"><h4>Result</h4><div class="hint" style="padding:10px">No trades. The rules were met ${r.sigs.length} time${r.sigs.length === 1 ? '' : 's'} on ${r.bars} bars. Loosen a rule or widen the test range.</div></div>`;
  const demo = /demo|synthetic/i.test((D.name || '') + (D.kind || '')) ? `<div class="hint" style="color:var(--warn);margin:6px 0">This is the built-in synthetic demo data. These numbers only show the tool working. They say nothing about any real market. Load real bars with Data.</div>` : '';
  const tile = (k, v, c = '') => `<div class="sttile"><div class="hint">${k}</div><div class="mono ${c}">${v}</div></div>`, mx = Math.max(...s.curve), mn = Math.min(...s.curve), W = 560, H = 90;
  const pts = s.curve.map((v, i) => `${(i / Math.max(1, s.curve.length - 1) * W).toFixed(1)},${(H - (v - mn) / Math.max(1, mx - mn) * (H - 8) - 4).toFixed(1)}`).join(' ');
  const cut = Math.floor(r.trades.length * 0.7), a = sStats(r.trades.slice(0, cut)), b = sStats(r.trades.slice(cut));
  const half = a && b && r.trades.length >= 20 ? `<div class="hint" style="margin-top:8px">First 70% of trades: ${money(a.net)} · PF ${a.pf == null ? '-' : a.pf.toFixed(2)}. Last 30%: ${money(b.net)} · PF ${b.pf == null ? '-' : b.pf.toFixed(2)}. A rule set that only works on one part of the data is a warning sign.</div>` : '';
  const rows = r.trades.slice(-200).map((t, k) => { const n = r.trades.length - Math.min(200, r.trades.length) + k; return `<tr><td>${new Date(D.dt[t.e] * 1000).toISOString().slice(5, 16).replace('T', ' ')}</td><td>${t.d > 0 ? 'Long' : 'Short'}</td><td class="mono">${t.qty}</td><td class="mono">${fx(t.entry)}</td><td class="mono">${fx(t.exit)}</td><td>${t.why}</td><td class="mono ${t.pnl >= 0 ? 'pos' : 'neg'}">${money(t.pnl)}</td><td class="mono">${t.r.toFixed(2)}R</td><td><button class="xs" data-go="${n}">View</button></td></tr>`; }).join('');
  return `<div class="an"><h4>Result · ${s.n} trades on ${r.bars.toLocaleString()} bars</h4>${demo}
  <div class="stgrid">${tile('Net', money(s.net), s.net >= 0 ? 'pos' : 'neg')}${tile('Win rate', (s.wr * 100).toFixed(0) + '%')}${tile('Profit factor', s.pf == null ? 'n/a' : s.pf.toFixed(2))}${tile('Avg R', s.avgR.toFixed(2) + 'R')}${tile('Max drawdown', money(-s.dd, false))}${tile('Avg win / loss', money(s.avgW, false) + ' / ' + money(s.avgL, false))}${tile('Longest loss streak', s.mls)}${tile('Best / worst', money(s.best, false) + ' / ' + money(s.worst, false))}</div>
  <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:90px;margin-top:10px"><polyline fill="none" stroke="#7aa2ff" stroke-width="1.6" points="${pts}"/></svg>${half}
  <div class="strow" style="margin-top:8px"><label class="chk"><input type="checkbox" id="stSigOn" ${X.sigOn ? 'checked' : ''}>Show where the rules were met on the chart while replaying</label></div>
  <div style="max-height:230px;overflow:auto;margin-top:8px"><table><tr><th>Entry (ET)</th><th>Side</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Exit by</th><th>P&amp;L</th><th>R</th><th></th></tr>${rows}</table></div></div>`;
}
function stSet(path, v) {
  const p = path.split('.'); let o = ST;
  if (p[0] === 'c') { o = ST.conds[+p[1]]; const k = p[2]; if (k === 't') { ST.conds[+p[1]] = { t: v, ...CS[v].d }; return true; } o[k] = CS[o.t].f.find(f => f[0] === k)?.[1] === 'num' ? +v : v; return false; }
  if (p[0] === 'stop' || p[0] === 'tgt') { o = ST[p[0]]; if (p[1] === 't') { o.t = v; if (p[0] === 'tgt' && v === 'pts') o.v = 40; if (p[0] === 'tgt' && v === 'r') o.v = 2; if (p[0] === 'stop' && v === 'atr') o.v = 1.5; if (p[0] === 'stop' && v === 'pts') o.v = 20; return true; } o.v = +v; return false; }
  if (path === 'riskOn') { ST.riskOn = v === '1'; return true; }
  if (['tf', 'be', 'maxHold', 'maxDay', 'dayLoss', 'qty', 'risk'].includes(path)) ST[path] = +v; else ST[path] = v;
  return path === 'dir' ? false : false;
}
function stRender() { $('#mBody').innerHTML = stHtml(); $('#stRes').innerHTML = stResHtml(); }
function stRun() {
  if (!D) return; stSave(); const t0 = performance.now();
  try { SRES = sRun(ST); } catch (e) { toast('Could not run these rules: ' + e.message, 'var(--warn)'); return; }
  X.sig = SRES.sigs; $('#stRes').innerHTML = stResHtml(); $('#stRes').scrollIntoView({ block: 'nearest' }); if (X.sigOn) dirty.markers = true; drawOv();
  const ms = Math.round(performance.now() - t0); if (ms > 4000) toast(`That took ${(ms / 1000).toFixed(1)} s. A larger timeframe runs faster.`);
}
function openStrategy() {
  if (!D) return; if (D.baseSec >= 86400) { toast('The rule tester needs intraday data', 'var(--warn)'); return; }
  if (ST.tf < D.baseSec || ST.tf % D.baseSec) ST.tf = tf >= D.baseSec ? tf : D.baseSec;
  modal('Strategy builder', stHtml(), [['Close', null], ['Export CSV', () => { stCsv(); return false; }], ['Run test', () => { stRun(); return false; }, 'primary']]);
  $('#modal .modal').style.maxWidth = 'min(980px, 96vw)'; $('#modal .modal').style.width = '980px'; $('#stRes').innerHTML = stResHtml();
}
function stCsv() {
  if (!SRES || !SRES.trades.length) { toast('Run a test first'); return; }
  const rows = [['entry_et', 'side', 'qty', 'entry', 'exit', 'exit_by', 'pnl', 'r'].join(',')].concat(SRES.trades.map(t => [new Date(D.dt[t.e] * 1000).toISOString().slice(0, 19), t.d > 0 ? 'long' : 'short', t.qty, t.entry, t.exit, t.why, t.pnl.toFixed(2), t.r.toFixed(3)].join(',')));
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' })); a.download = (ST.name || 'rules').replace(/\W+/g, '_') + '.csv'; a.click();
}
$('#mBody').addEventListener('change', e => {
  const t = e.target; if (!t.closest('.stb')) return;
  if (t.id === 'stPre') { const p = STPRE[t.value]; if (p) { ST = Object.assign(sdef(), { name: t.value === 'Blank' ? 'My rules' : t.value }, JSON.parse(JSON.stringify(p))); if (ST.tf < D.baseSec || ST.tf % D.baseSec) ST.tf = D.baseSec; SRES = null; X.sig = []; stSave(); stRender(); } return; }
  if (t.id === 'stSigOn') { X.sigOn = t.checked; drawOv(); return; }
  if (t.dataset.k == null) return;
  const re = stSet(t.dataset.k, t.value); stSave(); if (re) stRender();
});
$('#mBody').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b || !b.closest('.stb')) return;
  if (b.id === 'stAdd') { ST.conds.push({ t: 'vwap' }); stSave(); stRender(); }
  else if (b.dataset.del != null) { ST.conds.splice(+b.dataset.del, 1); stSave(); stRender(); }
  else if (b.dataset.go != null) { const t = SRES && SRES.trades[+b.dataset.go]; if (t) stView(t); }
  else if (b.id === 'stSaveBtn') { const l = stList(), n = (ST.name || 'My rules').trim(), i = l.findIndex(x => x.name === n), v = { name: n, def: JSON.parse(JSON.stringify(ST)) }; if (i >= 0) l[i] = v; else l.push(v); try { localStorage.setItem(SKEY, JSON.stringify(l)); } catch (er) { } toast('Saved "' + n + '"'); stRender(); }
  else if (b.id === 'stLoad') { const v = $('#stSaved').value; const l = stList(); if (v !== '' && l[+v]) { ST = Object.assign(sdef(), l[+v].def); SRES = null; stSave(); stRender(); } }
  else if (b.id === 'stDelS') { const v = $('#stSaved').value; const l = stList(); if (v !== '' && l[+v]) { l.splice(+v, 1); try { localStorage.setItem(SKEY, JSON.stringify(l)); } catch (er) { } stRender(); } }
});
$('#bStrat').onclick = openStrategy;
