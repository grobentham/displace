/* ============================== v6: trade review, observations, calendar, own rules, scale-out ============================== */
const NEW6 = { maxTrades: 0, dayLoss: 0, kzOnly: false };
Object.assign(DEF, NEW6); for (const k in NEW6) if (!(k in S)) S[k] = NEW6[k];
X.view = null;
const dur = s => { const m = Math.round(s / 60); return m >= 120 ? (m / 60).toFixed(1) + ' h' : m + ' min'; };
const dayKey = t => Math.floor((toET(t) + 21600) / 86400);

/* ---------- your own rules ---------- */
function riskBlock() {
  if (!D) return '';
  const sk = Math.floor((D.dt[cur] + 21600) / 86400);
  if (S.maxTrades > 0) { const seen = new Set(); for (const c of closed.concat(trades)) if (dayKey(c.entryT) === sk) seen.add(c.entryT + '|' + c.entry + '|' + c.side); if (seen.size >= S.maxTrades) return `Your rule: at most ${S.maxTrades} trade${S.maxTrades > 1 ? 's' : ''} per day. That limit is reached.`; }
  if (S.dayLoss > 0 && acct().day <= -S.dayLoss) return `Your rule: stop after losing ${money(S.dayLoss, false)} in a day. That limit is reached.`;
  if (S.kzOnly && D.baseSec < 3600) { const m = todMin(D.dt[cur]); if (!KZ.some(z => m >= z[0] && m < z[1])) return 'Your rule: new orders only inside the kill zones. It is outside them now.'; }
  return '';
}

/* ---------- scale out at a first target ---------- */
const scNow = () => ($('#scOn') && $('#scOn').checked) ? { pts: Math.max(0.25, +$('#scPts').value || 20), pct: Math.min(90, Math.max(10, +$('#scPct').value || 50)) } : null;
function scaleOut(tr, i) {
  if (!tr.sc || tr.scDone || tr.qty < 2) return; const L = tr.side > 0, tgt = rt(tr.entry + tr.side * tr.sc.pts);
  if (!(L ? D.h[i] >= tgt : D.l[i] <= tgt)) return; tr.scDone = true;
  const q = Math.max(1, Math.floor(tr.qty * tr.sc.pct / 100)); if (q >= tr.qty) return;
  closePart(tr, q, tgt, D.t[i], 'Scale-out'); const ns = rt(tr.entry);
  if (tr.sl == null || (L ? ns > tr.sl : ns < tr.sl)) tr.sl = ns; dirty.pos = dirty.lines = true; toast(`Took ${q} off at ${fx(tgt)}. Stop moved to breakeven`);
}

/* ---------- review a closed trade on the chart ---------- */
function idxOfT(t) { let lo = 0, hi = agg.length - 1, r = 0; while (lo <= hi) { const m = (lo + hi) >> 1; if (agg[m].time <= t) { r = m; lo = m + 1; } else hi = m - 1; } return r; }
function viewTrade(id) {
  const c = closed.find(x => x.id === id); if (!c) return;
  if (c.exitT > D.t[cur] || c.entryT < D.t[0]) { toast('Move the replay to that time first, then review it', 'var(--warn)'); return; }
  X.view = c; const a = idxOfT(toET(c.entryT)), b = idxOfT(toET(c.exitT));
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, a - 50), to: Math.min(agg.length + 10, b + 40) });
  banner(`Reviewing ${c.side > 0 ? 'long' : 'short'} ${c.qty} · ${money(c.pnl)} · press Esc or step the replay to clear`);
}
function drawView(P) {
  const c = X.view, A = ptXY({ t: toET(c.entryT), p: c.entry }), B = ptXY({ t: toET(c.exitT), p: c.exit }); if (!A || !B) return;
  const win = c.pnl >= 0, col = win ? '#22c38e' : '#f0516a'; og.setLineDash([]);
  og.fillStyle = win ? 'rgba(34,195,142,.12)' : 'rgba(240,81,106,.12)'; og.fillRect(A.x, Math.min(A.y, B.y), B.x - A.x, Math.abs(B.y - A.y) || 2);
  og.strokeStyle = col; og.lineWidth = 1.75; og.beginPath(); og.moveTo(A.x, A.y); og.lineTo(B.x, B.y); og.stroke();
  for (const q of [A, B]) { og.fillStyle = '#0b0d12'; og.beginPath(); og.arc(q.x, q.y, 4.5, 0, 7); og.fill(); og.stroke(); }
  const seg = (p, color, label) => { const y = candle.priceToCoordinate(p); if (y == null) return; og.strokeStyle = color; og.lineWidth = 1; og.setLineDash([4, 4]); og.beginPath(); og.moveTo(A.x, y); og.lineTo(Math.max(B.x, A.x + 40), y); og.stroke(); og.setLineDash([]); og.fillStyle = color; og.fillText(label + ' ' + fx(p), A.x + 4, y - 7); };
  if (c.initSL != null) seg(c.initSL, '#f0516a', 'Stop'); if (c.tp != null) seg(c.tp, '#22c38e', 'Target');
  const t = `${c.side > 0 ? 'Long' : 'Short'} ${c.qty} · ${money(c.pnl)}${c.r != null ? ' · ' + c.r.toFixed(2) + 'R' : ''} · ${c.reason} · held ${dur(c.exitT - c.entryT)}`, tw = og.measureText(t).width;
  const tx = Math.min(Math.max(6, (A.x + B.x) / 2 - tw / 2), P.w - tw - 14), ty = Math.max(14, Math.min(A.y, B.y) - 16);
  og.fillStyle = '#1b2130'; og.fillRect(tx - 6, ty - 9, tw + 12, 18); og.fillStyle = '#d7dce5'; og.fillText(t, tx, ty);
}
$('#histPane').addEventListener('click', e => { const b = e.target.closest('button[data-v]'); if (b) viewTrade(+b.dataset.v); });
const _adv6 = advance; advance = function (n, q) { if (X.view) { X.view = null; banner(''); } return _adv6(n, q); };
document.addEventListener('keydown', e => { if (e.key === 'Escape' && X.view) { X.view = null; banner(''); } });

/* ---------- observations and calendar ---------- */
function insightsHtml() {
  const n = closed.length;
  if (n < 8) return `<div class="anins"><span>Observations appear after 8 closed trades. You have ${n}.</span></div>`;
  const w = closed.filter(c => c.pnl > 0), l = closed.filter(c => c.pnl < 0), avg = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0, out = [];
  const net = closed.reduce((s, c) => s + c.pnl, 0), gp = w.reduce((s, c) => s + c.pnl, 0), gl = -l.reduce((s, c) => s + c.pnl, 0);
  out.push(`Across ${n} trades: net ${money(net)}, win rate ${(w.length / n * 100).toFixed(0)}%, profit factor ${gl > 0 ? (gp / gl).toFixed(2) : 'not defined yet'}.`);
  const aw = avg(w.map(c => c.pnl)), al = -avg(l.map(c => c.pnl));
  if (w.length >= 3 && l.length >= 3 && aw < al) out.push(`The average win (${money(aw, false)}) is smaller than the average loss (${money(al, false)}). That can mean winners are closed early or stops are wide, and it is worth reviewing.`);
  const hw = avg(w.map(c => c.exitT - c.entryT)), hl = avg(l.map(c => c.exitT - c.entryT));
  if (w.length >= 3 && l.length >= 3 && hl > hw * 1.5) out.push(`Losing trades were held about ${dur(hl)} on average, against ${dur(hw)} for winners.`);
  const mf = w.filter(c => c.mfe > 0); if (mf.length >= 3) out.push(`On winners, the exit captured about ${(avg(mf.map(c => Math.min(1, c.pts / c.mfe))) * 100).toFixed(0)}% of the best price reached while the trade was open.`);
  const srt = closed.slice().sort((a, b) => a.entryT - b.entryT), aft = [], oth = [];
  for (let k = 1; k < srt.length; k++) (srt[k - 1].pnl < 0 && srt[k].entryT - srt[k - 1].exitT <= 1800 ? aft : oth).push(srt[k].pnl);
  if (aft.length >= 5 && oth.length >= 5) out.push(`Trades taken within 30 minutes of a loss averaged ${money(avg(aft))} per trade, against ${money(avg(oth))} otherwise.`);
  const ns = closed.filter(c => c.initSL == null).length; if (ns) out.push(`${ns} of ${n} trades had no stop at entry.`);
  const q = closed.map(c => c.qty).sort((a, b) => a - b); if (q[q.length - 1] >= 2 * Math.max(1, q[Math.floor(q.length / 2)])) out.push(`Position size varied from ${q[0]} to ${q[q.length - 1]} contracts.`);
  const fo = closed.filter(c => c.rules === 'followed'), no = closed.filter(c => c.rules !== 'followed'); if (fo.length >= 4 && no.length >= 4) out.push(`With the checklist followed, trades averaged ${money(avg(fo.map(c => c.pnl)))}. Without it, ${money(avg(no.map(c => c.pnl)))}.`);
  return `<div class="anins" style="flex-direction:column;gap:6px"><b style="color:var(--text)">What your trades say</b>${out.map(t => `<span>${t}</span>`).join('')}<span class="hint">These are observations from your own results, for review. They are not advice.</span></div>`;
}
function calHtml() {
  if (!closed.length) return '';
  const m = new Map(); for (const c of closed) { const k = Math.floor((toET(c.exitT) + 21600) / 86400); m.set(k, (m.get(k) || 0) + c.pnl); }
  const keys = [...m.keys()].sort((a, b) => a - b), last = keys[keys.length - 1], wk = k => Math.floor((k - 4) / 7), lastW = wk(last), mx = Math.max(1, ...[...m.values()].map(Math.abs));
  let rows = '';
  for (let w = Math.max(wk(keys[0]), lastW - 9); w <= lastW; w++) {
    let cells = ''; for (let d = 0; d < 5; d++) { const k = w * 7 + 4 + d, v = m.get(k), dt = new Date(k * 86400000);
      const bg = v == null ? 'transparent' : v >= 0 ? `rgba(34,195,142,${(0.12 + 0.55 * Math.abs(v) / mx).toFixed(2)})` : `rgba(240,81,106,${(0.12 + 0.55 * Math.abs(v) / mx).toFixed(2)})`;
      cells += `<td style="background:${bg};text-align:center;padding:4px 2px" title="${dt.toISOString().slice(0, 10)}"><div class="mut" style="font-size:9.5px">${dt.getUTCMonth() + 1}/${dt.getUTCDate()}</div><div style="font-size:11px">${v == null ? '' : money(v, false).replace(/\.\d\d$/, '')}</div></td>`; }
    rows += `<tr>${cells}</tr>`;
  }
  return `<div class="an"><h4>Daily P&amp;L calendar</h4><table style="table-layout:fixed"><tr>${['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].map(d => `<th style="text-align:center">${d}</th>`).join('')}</tr>${rows}</table></div>`;
}
