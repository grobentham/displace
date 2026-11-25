/* Read Iron Brain's public market summaries. Each card keeps the source's own timestamps. */
(function () {
  "use strict";
  const stamp = document.getElementById("ib-outlook-stamp");
  const body = document.getElementById("ib-outlook-body");
  const buttons = document.querySelectorAll("[data-ib-market]");
  if (!body) return;

  const source = "https://raw.githubusercontent.com/grobentham/iron-brain/quotes/quotes.json";
  const names = { nq: "NQ", es: "ES", xauusd: "XAUUSD" };
  const labels = { bullish: "Bullish", bearish: "Bearish", consolidating: "Consolidating", mixed: "Mixed" };
  const sources = { nq: "NQ futures", es: "ES futures", xauusd: "Dukascopy spot gold bid" };
  const prices = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const local = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  let selected = "nq";
  let feed, failed = false, busy = false;
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
      col.append(node("h3", "", label));
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
    const market = selected === "nq" ? feed : feed?.markets?.[selected];
    const title = node("h2", "ib-outlook-heading", names[selected] + " market outlook");
    body.replaceChildren(title);
    if (!market || !Number.isFinite(Date.parse(market.barTime)) || !Number.isFinite(Date.parse(market.time))) {
      stamp.textContent = failed ? "Iron Brain feed unavailable" : "Source: Iron Brain";
      body.append(node("p", "ib-outlook-message", feed || failed
        ? names[selected] + " outlook is currently unavailable."
        : "Loading the " + names[selected] + " outlook…"));
      return;
    }
    const age = Math.max(0, Math.floor((Date.now() - Date.parse(market.time)) / 60000));
    const barAge = (Date.now() - Date.parse(market.barTime)) / 60000;
    const stale = age > 20 || barAge > 35;
    stamp.textContent = sources[selected] + " · Prices as of " + local.format(new Date(market.barTime))
      + (stale || failed ? " · Last available snapshot" : " · Updated " + (age < 1 ? "just now" : age + " min ago"));

    if (labels[market.lean]) {
      const banner = node("p", "ib-outlook-lean");
      banner.dataset.lean = market.lean;
      banner.append(node("strong", "", labels[market.lean]));
      if (market.leanText) banner.append(document.createTextNode(market.leanText));
      body.append(banner);
    }
    if (market.phaseText) body.append(node("p", "ib-outlook-phase", market.phaseText));
    const notes = node("ul", "ib-outlook-lines");
    for (const line of Array.isArray(market.lines) ? market.lines : []) {
      if (typeof line === "string" && line !== market.leanText) notes.append(node("li", "", line));
    }
    if (notes.childElementCount) body.append(notes);
    body.append(levels(market));
  }

  async function refresh() {
    if (busy || document.hidden || window.__page !== "intraday-bias") return;
    if (Date.now() - lastAttempt < 60000) return;
    lastAttempt = Date.now();
    busy = true;
    try {
      const url = source + "?minute=" + Math.floor(Date.now() / 60000);
      const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw Error("Iron Brain feed unavailable");
      const payload = await response.json();
      if (!payload.outlook) throw Error("Iron Brain outlook missing");
      feed = payload.outlook;
      failed = false;
    } catch (error) {
      failed = true;
    } finally {
      busy = false;
      render();
    }
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
