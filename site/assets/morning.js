/* Morning check: the first thing on Displace. For a futures trader before the New York open:
   how big today could get, which of yesterday's levels are likely to go, the news that moves it,
   and what that means for their own account. Evidence comes from the verified forecast ledger. */
(function () {
  "use strict";
  var MARKETS = [["nq", "NQ"], ["es", "ES"], ["gold", "Gold"]];
  var root = document.getElementById("mc");
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var B = null, EV = [], evidence, review, highImpact = [], calendarAvailable = false;
  var outlook = window.DisplaceOutlook, calendar = window.ECON;
  var store = {
    get: function () { try { return localStorage.getItem("mc.m") || "nq"; } catch (e) { return "nq"; } },
    set: function (market) { try { localStorage.setItem("mc.m", market); } catch (e) {} }
  };
  var sharedMarket = new URLSearchParams(location.search).get("market");
  var mk = MARKETS.some(function (market) { return market[0] === sharedMarket; }) ? sharedMarket : store.get();
  var seen = new Map();

  function num(x, dp) { return Number(x).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }); }
  function pts(x, market) { return outlook.formatPoints(x, market); }
  function pc(p) { return Math.round(100 * p) + "%"; }

  function dayName(iso) { return new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" }); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  function renderEvidence() {
    $("mc-evidence").textContent = outlook.scoringStatus(evidence, mk);
    renderReview();
  }

  function localRead(key) {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (_) { return null; }
  }

  function reviewKey() { return "displace.review." + review.market + "." + review.for; }

  function renderReview() {
    if (!B || evidence === undefined) return;
    var market = B.markets[mk], now = Date.now();
    var previous = (evidence?.forecasts || []).filter(function (row) {
      return row.market === mk && row.status === "verified_resolved" && Date.parse(row.for + "T00:00:00Z") <= now;
    }).sort(function (a, b) { return b.for.localeCompare(a.for); })[0];
    var results = $("mc-review-results"), notes = $("mc-review-form"), news = $("mc-review-news");
    results.hidden = notes.hidden = $("mc-review-link").hidden = !previous;
    results.replaceChildren(); news.replaceChildren(); news.hidden = true;
    $("mc-review-summary").textContent = previous ? market.name + " · " + dayName(previous.for) + " · Latest verified outcome" :
      evidence ? "A verified market outcome will appear here after it is scored." : "The forecast record is temporarily unavailable.";
    if (!previous) { review = null; return; }
    var items = [
      ["Forecast band", pts(previous.range_lo, market) + "–" + pts(previous.range_hi, market) + " points"],
      ["Actual range", Number.isFinite(previous.actual_range) ? pts(previous.actual_range, market) + " points" : previous.inRange ? "Inside the band" : "Outside the band"],
      ["Prior high", previous.highTaken ? "Traded through" : "Held"],
      ["Prior low", previous.lowTaken ? "Traded through" : "Held"]
    ];
    items.forEach(function (item) {
      var box = el("div"); box.append(el("dt", "", item[0]), el("dd", "", item[1])); results.append(box);
    });
    EV.filter(function (event) { return event.date === previous.for && event.impact === "high" && event.actual; }).forEach(function (event) {
      news.append(el("li", "", event.title + " · " + event.actual + " actual" + (event.forecast ? " · " + event.forecast + " consensus" : "")));
    });
    news.hidden = !news.children.length;
    if (review?.id !== previous.id) {
      review = previous;
      $("mc-review-note").value = localRead(reviewKey()) || "";
      $("mc-review-status").textContent = "";
    }
  }

  function nextRelease() {
    return EV.filter(function (event) { return event.impact === "high" && event.time && calendar.instant(event.date, event.time) > Date.now(); })
      .sort(function (a, b) { return calendar.instant(a.date, a.time) - calendar.instant(b.date, b.time); })[0];
  }

  function renderNext(day, session) {
    var event = nextRelease(), line = $("mc-next"), change = $("mc-change");
    line.hidden = !event && calendarAvailable;
    line.textContent = event ? "Next high-impact release · " + event.title + " · " + calendar.localDayLabel(event) + " at " + calendar.local(event) : "Release calendar temporarily unavailable.";
    var key = "displace.outlook-seen." + mk;
    if (!seen.has(mk)) seen.set(mk, localRead(key));
    var before = seen.get(mk), instant = event && calendar.instant(event.date, event.time);
    var message = "";
    if (before?.day && before.day !== day) message = "Since your last visit · New session outlook.";
    else if (event && before?.release === event.title && before.instant !== instant) message = "Since your last visit · " + event.title + " was rescheduled.";
    else if (before?.open && (before.open !== session?.open || before.close !== session?.close)) message = "Since your last visit · Session hours changed.";
    change.textContent = message; change.hidden = !message;
    if (calendarAvailable) {
      try { localStorage.setItem(key, JSON.stringify({ day: day, release: event?.title, instant: instant, open: session?.open, close: session?.close })); } catch (_) {}
    }
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

  function renderSessionPhase() {
    var badge = $("mc-phase-badge");
    if (!badge || !B) return;
    var phase = outlook.sessionPhase(B.markets[mk]?.session);
    badge.textContent = phase;
    badge.className = "mc-chip " + (phase === "In session" ? "ok" : phase === "Upcoming" ? "" : "warn");
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
    $("mc-heading").textContent = "Plan your " + m.name + " session in 60 seconds";
    $("mc-pts").textContent = pts(r.points, m);
    $("mc-range").textContent = "80% range band: " + pts(r.lo, m) + "–" + pts(r.hi, m) + " points.";
    var lean = outlook.directionLean(m);
    $("mc-lean").hidden = !lean;
    if (lean) {
      $("mc-lean-label").textContent = lean.label;
      $("mc-lean-context").textContent = lean.historical
        ? "Historical base rate · " + lean.percent + " of sessions closed above their prior close."
        : "Model estimate · " + lean.percent + " chance of closing above the prior close.";
    }
    var windowLabel = outlook.sessionWindow(m.session), session = $("mc-window");
    session.hidden = !windowLabel;
    session.textContent = windowLabel ? "Session hours · " + windowLabel : "";
    renderNext(day, m.session);
    renderShare(m, day);
    renderEvidence();
    var cmp = $("mc-cmp"); cmp.textContent = "";
    if (r.med250) {
      var x = r.points / r.med250;
      cmp.textContent = (x >= 1.5 ? "Much bigger than a normal day" : x >= 1.15 ? "Bigger than a normal day" : x <= 0.8 ? "Quieter than a normal day" : "About a normal day") +
        " (past-year median: " + pts(r.med250, m) + " · last 20 sessions average: " + pts(r.avg20, m) + ").";
    }

    // day status: holidays and big releases on the session date
    var today = EV.filter(function (e) {
      if (e.date === day) return true;
      if (!e.time || !m.session?.open || !m.session.close) return false;
      var at = calendar.instant(e.date, e.time);
      return at >= Date.parse(m.session.open) && at < Date.parse(m.session.close);
    });
    var hol = EV.find(function (e) { return e.date === day && e.impact === "holiday"; });
    highImpact = today.filter(function (e) { return e.impact === "high" && e.time && e.id; })
      .sort(function (a, b) { return a.time.localeCompare(b.time); });
    var chips = $("mc-status"); chips.replaceChildren();
    var phaseBadge = el("span"); phaseBadge.id = "mc-phase-badge";
    chips.append(phaseBadge); renderSessionPhase();
    if (hol) chips.append(el("span", "mc-chip warn", hol.title.replace(/^[^:]*:\s*/, "").replace(/^./, function (c) { return c.toUpperCase(); }) + " (" + hol.title.split(":")[0] + ")"));
    if (highImpact.length) {
      var times = Array.from(new Set(highImpact.map(function (e) { return e.time; })));
      chips.append(el("span", "mc-chip warn", "Big news at " + times.join(" and ") + " New York"));
    }
    if (r.med250 && r.points / r.med250 >= 1.5) chips.append(el("span", "mc-chip warn", "Wide-range day"));

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
    if (!list.length) nw.append(el("p", "mc-muted", calendarAvailable ? "No major US releases scheduled for this session." : "Release calendar temporarily unavailable."));
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

  function renderShare(market, day) {
    var button = $("mc-share"), input = $("mc-share-url");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day || "")) return;
    var link = new URL("sessions/" + mk + "/" + day + ".html", document.baseURI);
    input.value = link.href;
    $("mc-share-preview").href = link.href;
    $("mc-share-status").textContent = "";
    button.textContent = "Share " + (mk === "nq" ? "MNQ" : market.name) + " brief";
    button.hidden = false;
  }

  function setupShare() {
    var button = $("mc-share"), panel = $("mc-share-panel"), input = $("mc-share-url"), status = $("mc-share-status");
    button.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      button.setAttribute("aria-expanded", String(!panel.hidden));
    });
    $("mc-copy").addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(input.value);
        status.textContent = "Public brief link copied.";
      } catch (error) {
        input.focus();
        input.select();
        status.textContent = "Link selected. Copy it to share.";
      }
    });
  }

  bind();
  setupShare();
  $("mc-review-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!review) return;
    try {
      localStorage.setItem(reviewKey(), JSON.stringify($("mc-review-note").value.trim()));
      $("mc-review-status").textContent = "Note saved on this device.";
    } catch (_) { $("mc-review-status").textContent = "This browser could not save the note."; }
  });
  window.addEventListener("displace:reminder-change", renderReminder);
  window.addEventListener("displace:route", renderReminder);
  setInterval(function () { renderReminder(); renderSessionPhase(); }, 30000);
  outlook.evidence().then(function (data) { evidence = data; renderEvidence(); });

  function get(p) { return fetch(p + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) { if (!r.ok) throw Error(p); return r.json(); }); }
  Promise.all([get("data/bias/current.json"), get("data/calendar/events.json").catch(function () { return null; })]).then(function (x) {
    B = x[0]; calendarAvailable = Array.isArray(x[1]?.events); EV = calendarAvailable ? x[1].events : [];
    var available = MARKETS.find(function (market) { return B.markets[market[0]]; });
    if (!available) throw Error("No markets available");
    if (!B.markets[mk]) mk = available[0];
    root.classList.add("ready"); render();
  }).catch(function () {
    $("mc-for").textContent = "Today's numbers are unavailable right now. Try again in a minute.";
    $("mc-plan-session").textContent = "Session data unavailable. Try refreshing.";
  });
})();
