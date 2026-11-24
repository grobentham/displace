/* Morning check: the first thing on Displace. For a futures trader before the New York open:
   how big today could get, which of yesterday's levels are likely to go, the news that moves it,
   and what that means for their own account. Data: data/bias/current.json, data/calendar/events.json. */
(function () {
  "use strict";
  var MARKETS = [["nq", "NQ"], ["es", "ES"], ["gold", "Gold"]];
  var MICRO = { nq: "MNQ", es: "MES", gold: "MGC" }, MINI = { nq: "NQ", es: "ES", gold: "GC" };
  var root = document.getElementById("mc");
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var B = null, EV = [];
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem("mc." + k); return v === null ? d : v; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem("mc." + k, v); } catch (e) {} }
  };
  var mk = store.get("m", "nq");

  function num(x, dp) { return Number(x).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }); }
  function round(x) { var s = x >= 1000 ? 10 : x >= 100 ? 5 : x >= 10 ? 1 : 0.1; return Math.round(x / s) * s; }
  function pts(x, m) { var r = round(x); return num(r, r < 10 ? 1 : 0); }
  function usd(x) { return "$" + Math.round(x).toLocaleString("en-US"); }
  function pc(p) { return Math.round(100 * p) + "%"; }

  // A New York wall-clock time -> a Date (so it can be shown in the visitor's own time)
  function nyDate(day, hm) {
    var p = (hm || "00:00").split(":"), guess = new Date(day + "T" + p[0] + ":" + p[1] + ":00Z");
    var ny = new Date(guess.toLocaleString("en-US", { timeZone: "America/New_York" }));
    var utc = new Date(guess.toLocaleString("en-US", { timeZone: "UTC" }));
    return new Date(guess.getTime() + (utc - ny));
  }
  function localTime(d) { return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
  function dayName(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" }); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  function render() {
    if (!B) return;
    var m = B.markets[mk] || B.markets.nq, day = B["for"], r = m.range;
    MARKETS.forEach(function (x) { var b = $("mc-t-" + x[0]); if (b) b.setAttribute("aria-selected", String(x[0] === mk)); });

    // 1. how big
    $("mc-for").textContent = m.name + " · " + dayName(day) + " session";
    $("mc-pts").textContent = pts(r.points, m);
    $("mc-range").textContent = "Most days like this (8 in 10) land between " + pts(r.lo, m) + " and " + pts(r.hi, m) + " points.";
    var cmp = $("mc-cmp"); cmp.textContent = "";
    if (r.med250) {
      var x = r.points / r.med250;
      cmp.textContent = (x >= 1.5 ? "Much bigger than a normal day" : x >= 1.15 ? "Bigger than a normal day" : x <= 0.8 ? "Quieter than a normal day" : "About a normal day") +
        " (past year: " + pts(r.med250, m) + "; last 20 sessions: " + pts(r.avg20, m) + ").";
    }

    // day status: holidays and big releases on the session date
    var today = EV.filter(function (e) { return e.date === day; });
    var hol = today.filter(function (e) { return e.impact === "holiday"; })[0];
    var big = today.filter(function (e) { return e.impact === "high" && e.time; });
    var chips = $("mc-status"); chips.replaceChildren();
    if (hol) chips.append(el("span", "mc-chip warn", hol.title.replace(/^[^:]*:\s*/, "").replace(/^./, function (c) { return c.toUpperCase(); }) + " (" + hol.title.split(":")[0] + ")"));
    if (big.length) {
      var times = Array.from(new Set(big.map(function (e) { return e.time; })));
      chips.append(el("span", "mc-chip warn", "Big news at " + times.join(" and ") + " New York"));
    }
    if (r.med250 && r.points / r.med250 >= 1.5) chips.append(el("span", "mc-chip warn", "Wide-range day"));
    if (!chips.children.length) chips.append(el("span", "mc-chip ok", "No big news, normal size"));

    // 2. yesterday's levels
    var lv = $("mc-levels"); lv.replaceChildren();
    [["high", "Yesterday's high"], ["low", "Yesterday's low"]].forEach(function (s) {
      var t = m.takes[s[0]], row = el("div", "mc-row");
      var p = el("div", "mc-p", pc(t.p)); p.classList.add(t.p >= t.base + 0.1 ? "up" : t.p <= t.base - 0.1 ? "dn" : "eq");
      var tx = el("div", "mc-rt");
      tx.append(el("b", "", s[1] + " " + num(m.levels[s[0]], m.dp)));
      tx.append(el("small", "", "chance it trades through today · a typical day: " + pc(t.base)));
      row.append(p, tx); lv.append(row);
    });

    // 3. the news that moves it, in the visitor's time
    var nw = $("mc-news"); nw.replaceChildren();
    var list = today.filter(function (e) { return e.impact !== "holiday" && (e.impact === "high" || e.impact === "medium"); });
    if (!list.length) nw.append(el("p", "mc-muted", "No major US releases scheduled for this session."));
    list.slice(0, 6).forEach(function (e) {
      var row = el("div", "mc-row"), when = e.time ? nyDate(day, e.time) : null;
      var tm = el("div", "mc-tm" + (e.impact === "high" ? " hi" : ""), when ? localTime(when) : "All day");
      var tx = el("div", "mc-rt");
      tx.append(el("b", "", e.title));
      tx.append(el("small", "", (e.time ? e.time + " New York" : "") + (e.forecast ? " · expected " + e.forecast : "") + (e.previous ? " · last " + e.previous : "")));
      row.append(tm, tx); nw.append(row);
    });

    account(m, r);
    var made = new Date(B.asof), age = (Date.now() - made) / 36e5;
    $("mc-made").textContent = "Forecast made " + made.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) + " your time" +
      (age > 40 ? " — older than usual; the next update may be late." : ".");
  }

  // 4. your account: the expected range in dollars against your daily loss limit
  function account(m, r) {
    var limit = parseFloat(store.get("limit", "")), n = Math.max(1, parseInt(store.get("n", "1"), 10) || 1);
    var size = store.get("size", "micro"), per = size === "mini" ? m.pv : m.micro, sym = size === "mini" ? MINI[mk] : MICRO[mk];
    $("mc-sym-micro").textContent = MICRO[mk]; $("mc-sym-mini").textContent = MINI[mk];
    var out = $("mc-acct"); out.replaceChildren();
    var full = r.points * per * n, stop = full / 4;
    out.append(el("p", "", "Today's expected range is worth " + usd(full) + " on " + n + " " + sym + "."));
    if (!(limit > 0)) { out.append(el("p", "mc-muted", "Enter your daily loss limit to see how much of it one loss could use.")); return; }
    var share = stop / limit, safe = Math.floor(limit / (r.points * per));
    var p = el("p", share > 0.5 ? "mc-warn" : "");
    p.textContent = "A stop a quarter of the range away (" + usd(stop) + ") would use " + pc(share) + " of your " + usd(limit) + " limit in one loss.";
    out.append(p);
    out.append(el("p", "mc-muted", safe >= 1
      ? "To keep one such loss under a quarter of your limit: " + safe + " " + sym + " or fewer."
      : "Even 1 " + sym + " risks more than a quarter of your limit on that stop today. A smaller contract, a tighter plan or a day off are all reasonable."));
  }

  function bind() {
    var tabs = $("mc-tabs");
    MARKETS.forEach(function (x) {
      var b = el("button", "", x[1]); b.type = "button"; b.id = "mc-t-" + x[0]; b.setAttribute("role", "tab");
      b.addEventListener("click", function () { mk = x[0]; store.set("m", mk); render(); });
      tabs.append(b);
    });
    var lim = $("mc-limit"), n = $("mc-n");
    lim.value = store.get("limit", ""); n.value = store.get("n", "1");
    var sz = store.get("size", "micro");
    root.querySelectorAll('input[name="mc-size"]').forEach(function (i) {
      i.checked = i.value === sz;
      i.addEventListener("change", function () { store.set("size", i.value); render(); });
    });
    lim.addEventListener("input", function () { store.set("limit", lim.value); render(); });
    n.addEventListener("input", function () { store.set("n", n.value); render(); });
  }

  bind();
  function get(p) { return fetch(p + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) { if (!r.ok) throw Error(p); return r.json(); }); }
  Promise.all([get("data/bias/current.json"), get("data/calendar/events.json").catch(function () { return { events: [] }; })]).then(function (x) {
    B = x[0]; EV = x[1].events || []; root.classList.add("ready"); render();
  }).catch(function () { $("mc-for").textContent = "Today's numbers are unavailable right now. Try again in a minute."; });
})();
