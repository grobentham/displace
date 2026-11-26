/* Read each market from its publisher. Cards retain the source's own timestamps. */
(function () {
  "use strict";
  const body = document.getElementById("ib-outlook-body");
  const buttons = document.querySelectorAll("[data-ib-market]");
  if (!body) return;

  const nqSource = "https://raw.githubusercontent.com/grobentham/iron-brain/quotes/quotes.json";
  const displaceSource = "https://raw.githubusercontent.com/grobentham/displace/intraday-outlook/outlook.json";
  const names = { nq: "NQ", es: "ES", xauusd: "XAUUSD" };
  const instruments = { nq: "Nasdaq-100 futures", es: "S&P 500 futures", xauusd: "Spot gold" };
  const labels = { bullish: "Bullish", bearish: "Bearish", consolidating: "Consolidating", mixed: "Mixed" };
  const sources = { nq: "NQ futures · delayed", es: "ES futures · delayed", xauusd: "Dukascopy spot gold bid" };
  const prices = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const local = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  let selected = "nq";
  let feeds = {}, failed = {}, busy = {};
  let lastAttempt = -Infinity;

  function node(tag, cls, text) {
    const value = document.createElement(tag);
    if (cls) value.className = cls;
    if (text != null) value.textContent = text;
    return value;
  }

  function levels(market) {
    const grid = node("div", "ib-outlook-levels");
    for (const [key, label] of [["above", "Above"], ["below", "Below"]]) {
      const col = node("div");
      col.append(node("h4", "", label));
      const list = node("dl");
      const entries = Array.isArray(market.levels?.[key]) ? market.levels[key] : [];
      for (const entry of entries) {
        if (typeof entry.name !== "string" || !Number.isFinite(entry.price)) continue;
        const row = node("div");
        row.append(node("dt", "", entry.name), node("dd", "", prices.format(entry.price)));
        list.append(row);
      }
      if (list.childElementCount) col.append(list);
      else col.append(node("p", "mc-muted", "No nearby levels listed."));
      grid.append(col);
    }
    return grid;
  }

  function render() {
    for (const button of buttons) button.setAttribute("aria-pressed", String(button.dataset.ibMarket === selected));
    const provider = selected === "nq" ? "nq" : "displace";
    const feed = feeds[provider];
    const market = selected === "nq" ? feed : feed?.[selected];
    const snapshot = node("div", "ib-outlook-snapshot");
    const title = node("h2", "ib-outlook-heading", instruments[selected]);
    body.replaceChildren(snapshot);
    if (!market || !Number.isFinite(Date.parse(market.barTime)) || !Number.isFinite(Date.parse(market.time))) {
      const message = node("p", "ib-outlook-message", failed[provider]
        ? names[selected] + " market feed is temporarily unavailable."
        : feed ? names[selected] + " outlook is currently unavailable."
          : "Loading the " + names[selected] + " outlook…");
      message.setAttribute("role", "status");
      snapshot.append(title, message);
      return;
    }

    const reading = node("div", "ib-outlook-reading");
    const quote = node("div");
    quote.append(title);
    if (Number.isFinite(market.last)) {
      quote.append(node("p", "ib-outlook-price", prices.format(market.last)));
      if (selected === "xauusd") quote.append(node("p", "ib-outlook-unit", "USD per troy ounce"));
    }
    reading.append(quote);
    if (labels[market.lean]) {
      const banner = node("p", "ib-outlook-lean");
      banner.dataset.lean = market.lean;
      banner.append(node("strong", "", labels[market.lean]));
      if (market.leanText) banner.append(node("span", "", market.leanText));
      reading.append(banner);
    }

    const age = Math.max(0, Math.floor((Date.now() - Date.parse(market.time)) / 60000));
    const barAge = (Date.now() - Date.parse(market.barTime)) / 60000;
    const sampledGold = selected === "xauusd" && market.source === "xaus";
    const stale = failed[provider] || age > 20 || barAge > (sampledGold ? 15 : 35);
    const stamp = node("div", "ib-outlook-meta");
    stamp.id = "ib-outlook-stamp";
    if (sampledGold) {
      const attribution = node("a", "", "XAUS indicative spot");
      attribution.href = "https://xaus.com/api/";
      stamp.append(attribution);
    } else {
      stamp.append(node("span", "", sources[selected]));
    }
    const time = node("time", "", "Prices as of " + local.format(new Date(market.barTime)));
    time.dateTime = market.barTime;
    const status = node("span", "", stale ? "Last available snapshot" : "Updated " + (age < 1 ? "just now" : age + " min ago"));
    status.dataset.stale = String(stale);
    stamp.append(time, status);
    snapshot.append(reading, stamp);

    const detail = node("div", "ib-outlook-detail");
    const context = node("div", "mc-card ib-outlook-panel");
    const summary = node("ul", "ib-outlook-lines");
    for (const line of Array.isArray(market.lines) ? market.lines : []) {
      if (typeof line === "string" && line !== market.leanText) summary.append(node("li", "", line));
    }
    if (market.phaseText || summary.childElementCount) {
      context.append(node("h3", "", "Session context"));
      if (market.phaseText) context.append(node("p", "ib-outlook-phase", market.phaseText));
      if (summary.childElementCount) context.append(summary);
      detail.append(context);
    }
    const nearby = node("div", "mc-card ib-outlook-panel");
    nearby.append(node("h3", "", "Nearby levels"), levels(market));
    detail.append(nearby);
    body.append(detail);
  }

  async function update(provider, source, field) {
    if (busy[provider]) return;
    busy[provider] = true;
    try {
      const url = source + "?minute=" + Math.floor(Date.now() / 60000);
      const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw Error("Market feed unavailable");
      const data = (await response.json())[field];
      if (!data) throw Error("Outlook missing");
      feeds[provider] = data;
      failed[provider] = false;
    } catch {
      failed[provider] = true;
    } finally {
      busy[provider] = false;
      render();
    }
  }

  function refresh() {
    if (document.hidden || window.__page !== "intraday-bias") return;
    if (Date.now() - lastAttempt < 60000) return;
    lastAttempt = Date.now();
    update("nq", nqSource, "outlook");
    update("displace", displaceSource, "markets");
  }

  for (const button of buttons) button.addEventListener("click", () => {
    selected = button.dataset.ibMarket;
    render();
  });
  render();
  refresh();
  setInterval(refresh, 60000);
  window.addEventListener("displace:route", refresh);
  document.addEventListener("visibilitychange", refresh);
})();
