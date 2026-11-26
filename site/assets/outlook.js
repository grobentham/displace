/* Presentation shared by the homepage and the full market outlook. */
window.DisplaceOutlook = (function () {
  "use strict";
  var snapshot;
  var ny = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  });

  function formatPoints(value, market) {
    if (value == null) return "–";
    if (market.group === "fx") return Math.round(value * 10000).toLocaleString("en-US");
    var decimals = market.group === "oil" ? 2 : market.dp === 1 ? 1 : 0;
    return Number(value).toLocaleString("en-US", { maximumFractionDigits: decimals });
  }

  function sessionWindow(session) {
    if (!session || !session.open) return "";
    var label = ny.format(new Date(session.open));
    label += session.close ? " to " + ny.format(new Date(session.close)) + " New York" : " New York · Close time unavailable";
    if (session.halts && session.halts.length) {
      label += " · Holiday halt at " + session.halts.map(function (at) { return ny.format(new Date(at)); }).join(" and ") + " New York";
    }
    return label;
  }

  function afterOpen(asof, session) {
    return !!(session && session.open && Date.parse(asof) >= Date.parse(session.open));
  }

  function sessionPhase(session, now = Date.now()) {
    if (!session?.open) return "Hours unavailable";
    if (now < Date.parse(session.open)) return "Upcoming";
    if (session.close && now >= Date.parse(session.close)) return "Ended";
    for (const halt of session.halts || []) {
      const start = Date.parse(halt);
      const reopen = Date.parse(halt.slice(0, 11) + "18:00:00" + halt.slice(19));
      if (now >= start && now < reopen) return "Holiday halt";
    }
    return session.close ? "In session" : "Close time unconfirmed";
  }
  function evidence() {
    if (!snapshot) {
      snapshot = fetch("data/open/current.json", { cache: "no-cache" })
        .then(function (response) { return response.ok ? response.json() : null; })
        .catch(function () { return null; });
    }
    return snapshot;
  }

  function scoringStatus(data, symbol) {
    if (data === undefined) return "Checking live scoring…";
    var market = data && data.by_market && data.by_market[symbol];
    if (!market || !Number.isInteger(market.n) || market.n < 0) return "Live scoring status unavailable";
    if (market.n === 0) return "Live scoring pending";
    return market.n.toLocaleString("en-US") + (market.n === 1 ? " verified forecast scored" : " verified forecasts scored");
  }

  return { formatPoints: formatPoints, sessionWindow: sessionWindow, afterOpen: afterOpen, sessionPhase: sessionPhase, evidence: evidence, scoringStatus: scoringStatus };
})();
