/* Morning check: the first thing on Displace. For a futures trader before the New York open:
   how big today could get, which of yesterday's levels are likely to go, the news that moves it,
   and what that means for their own account. Evidence comes from the verified forecast ledger. */
(function () {
  "use strict";
  var MARKETS = [["nq", "NQ"], ["es", "ES"], ["gold", "Gold"]];
  var root = document.getElementById("mc");
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var B = null, EV = [], evidence, highImpact = [];
  var outlook = window.DisplaceOutlook, calendar = window.ECON;
  var store = {
    get: function () { try { return localStorage.getItem("mc.m") || "nq"; } catch (e) { return "nq"; } },
    set: function (market) { try { localStorage.setItem("mc.m", market); } catch (e) {} }
  };
  var mk = store.get();

  function num(x, dp) { return Number(x).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }); }
  function pts(x, market) { return outlook.formatPoints(x, market); }
  function pc(p) { return Math.round(100 * p) + "%"; }

  function dayName(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" }); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  function renderEvidence() {
    $("mc-evidence").textContent = outlook.scoringStatus(evidence, mk);
  }

  function renderReminder() {
    var button = $("mc-reminder");
    var event = highImpact.find(function (e) { return calendar.instant(e.date, e.time) > Date.now(); });
    button.hidden = !event;
    if (!event) return;
    var state = calendar.reminderState(event);
    var label = state === "automatic" ? "Automatic reminder set" : state === "selected" ? "Reminder set" : "Remind me";
    button.dataset.bell = event.id;
    button.textContent = label;
    button.setAttribute("aria-label", label + " for " + event.title);
    button.setAttribute("aria-pressed", String(state !== "off"));
    button.disabled = state === "automatic";
  }

  function render() {
    if (!B || !B.markets[mk]) return;
    var m = B.markets[mk], day = m.session ? m.session.date : B["for"], r = m.range;
    MARKETS.forEach(function (x) {
      var button = $("mc-t-" + x[0]);
      button.disabled = !B.markets[x[0]];
      button.setAttribute("aria-selected", String(x[0] === mk));
    });

    // 1. how big
    $("mc-for").textContent = m.name + " · " + dayName(day) + " session";
    $("mc-pts").textContent = pts(r.points, m);
    $("mc-range").textContent = "80% range band: " + pts(r.lo, m) + "–" + pts(r.hi, m) + " points.";
    var windowLabel = outlook.sessionWindow(m.session), session = $("mc-window");
    session.hidden = !windowLabel;
    session.textContent = windowLabel ? "Session hours · " + windowLabel : "";
    renderEvidence();
    var cmp = $("mc-cmp"); cmp.textContent = "";
    if (r.med250) {
      var x = r.points / r.med250;
      cmp.textContent = (x >= 1.5 ? "Much bigger than a normal day" : x >= 1.15 ? "Bigger than a normal day" : x <= 0.8 ? "Quieter than a normal day" : "About a normal day") +
        " (past-year median: " + pts(r.med250, m) + " · last 20 sessions average: " + pts(r.avg20, m) + ").";
    }

    // day status: holidays and big releases on the session date
    var today = EV.filter(function (e) { return e.date === day; });
    var hol = today.filter(function (e) { return e.impact === "holiday"; })[0];
    highImpact = today.filter(function (e) { return e.impact === "high" && e.time && e.id; })
      .sort(function (a, b) { return a.time.localeCompare(b.time); });
    var chips = $("mc-status"); chips.replaceChildren();
    if (hol) chips.append(el("span", "mc-chip warn", hol.title.replace(/^[^:]*:\s*/, "").replace(/^./, function (c) { return c.toUpperCase(); }) + " (" + hol.title.split(":")[0] + ")"));
    if (highImpact.length) {
      var times = Array.from(new Set(highImpact.map(function (e) { return e.time; })));
      chips.append(el("span", "mc-chip warn", "Big news at " + times.join(" and ") + " New York"));
    }
    if (r.med250 && r.points / r.med250 >= 1.5) chips.append(el("span", "mc-chip warn", "Wide-range day"));
    if (!chips.children.length) chips.append(el("span", "mc-chip ok", "No big news, normal size"));

    // 2. yesterday's levels
    var lv = $("mc-levels"); lv.replaceChildren();
    [["high", "Prior session high"], ["low", "Prior session low"]].forEach(function (s) {
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
      var row = el("div", "mc-row");
      var tm = el(e.time ? "time" : "div", "mc-tm" + (e.impact === "high" ? " hi" : ""), e.time ? calendar.local(e) : "All day");
      if (e.time) {
        tm.dateTime = new Date(calendar.instant(e.date, e.time)).toISOString();
        if (calendar.localDay(e) !== e.date) tm.append(el("small", "mc-tm-day", calendar.localDayLabel(e)));
      }
      var tx = el("div", "mc-rt");
      tx.append(el("b", "", e.title));
      tx.append(el("small", "", (e.time ? e.time + " New York" : "") + (e.forecast ? " · expected " + e.forecast : "") + (e.previous ? " · last " + e.previous : "")));
      row.append(tm, tx); nw.append(row);
    });

    renderReminder();
    window.DisplaceSessionPlanner.setMarket(mk, m, day, dayName(day));
    var made = new Date(m.forecast_at || B.asof), age = (Date.now() - made) / 36e5;
    var ended = m.session && m.session.close ? Date.now() >= Date.parse(m.session.close) : age > 40;
    $("mc-made").textContent = "Forecast made " + made.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) + " your time" +
      (outlook.afterOpen(made, m.session) ? ". Generated after the open and excluded from prospective scoring." : ".") +
      (ended ? " This outlook is for a past session." : "");
  }

  function bind() {
    var tabs = $("mc-tabs");
    MARKETS.forEach(function (x) {
      var b = el("button", "", x[1]); b.type = "button"; b.id = "mc-t-" + x[0]; b.setAttribute("role", "tab");
      b.addEventListener("click", function () { mk = x[0]; store.set(mk); render(); });
      tabs.append(b);
    });
  }

  function setupShare() {
    var button = $("mc-share"), panel = $("mc-share-panel"), input = $("mc-share-url"), status = $("mc-share-status");
    var market = B.markets.nq, day = market && (market.session ? market.session.date : B["for"]);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day || "")) return;
    var link = new URL("mnq-brief.html", document.baseURI);
    link.searchParams.set("date", day);
    input.value = link.href;
    $("mc-share-preview").href = link.href;
    button.hidden = false;

    button.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      button.setAttribute("aria-expanded", String(!panel.hidden));
    });
    $("mc-copy").addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(link.href);
        status.textContent = "Public brief link copied.";
      } catch (error) {
        input.focus();
        input.select();
        status.textContent = "Link selected. Copy it to share.";
      }
    });
  }

  bind();
  window.addEventListener("displace:reminder-change", renderReminder);
  window.addEventListener("displace:route", renderReminder);
  setInterval(renderReminder, 30000);
  outlook.evidence().then(function (data) { evidence = data; renderEvidence(); });

  function get(p) { return fetch(p + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) { if (!r.ok) throw Error(p); return r.json(); }); }
  Promise.all([get("data/bias/current.json"), get("data/calendar/events.json").catch(function () { return { events: [] }; })]).then(function (x) {
    B = x[0]; EV = x[1].events || [];
    var available = MARKETS.find(function (market) { return B.markets[market[0]]; });
    if (!available) throw Error("No markets available");
    if (!B.markets[mk]) mk = available[0];
    root.classList.add("ready"); render(); setupShare();
  }).catch(function () {
    $("mc-for").textContent = "Today's numbers are unavailable right now. Try again in a minute.";
    $("mc-plan-session").textContent = "Session data unavailable. Try refreshing.";
  });
})();
