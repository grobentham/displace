/* A public session brief uses date-addressed snapshots and the visitor's local timezone. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const outlook = window.DisplaceOutlook;
  const dayLabel = new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC", weekday: "long", month: "long", day: "numeric", year: "numeric"
  });
  const localLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"
  });
  const price = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const integerPoints = value => outlook.formatPoints(value, { group: "equity", dp: 2 });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function render(data) {
    const dateText = dayLabel.format(new Date(data.date + "T12:00:00Z"));
    $("brief-date").textContent = dateText + " · Nasdaq-100 futures";
    document.title = "MNQ session brief · " + dateText + " · Displace";
    $("brief-range").textContent = integerPoints(data.range.points);
    $("brief-band").textContent = "80% range band: " + integerPoints(data.range.lo) + "–" + integerPoints(data.range.hi) + " points.";
    $("brief-evidence").textContent = outlook.scoringStatus({ by_market: { nq: { n: data.live_count } } }, "nq");
    const hours = outlook.sessionWindow(data.session);
    $("brief-hours").textContent = hours ? "Session hours · " + hours : "";
    $("brief-hours").hidden = !hours;
    $("brief-asof").textContent = "Forecast made " + localLabel.format(new Date(data.asof)) + ". Estimates for the full session." +
      (outlook.afterOpen(data.asof, data.session) ? " Generated after the open and excluded from prospective scoring." : "");

    const levels = $("brief-levels");
    for (const key of ["high", "low"]) {
      const level = data.levels[key];
      const row = element("div", "mc-row");
      const copy = element("div", "mc-rt");
      const probability = level.probability == null ? "—" : Math.round(level.probability * 100) + "%";
      copy.append(element("b", "", "Prior " + key + " " + (level.price == null ? "—" : price.format(level.price))));
      copy.append(element("small", "", "Estimated chance of trading through this level"));
      row.append(element("div", "mc-p", probability), copy);
      levels.append(row);
    }

    const news = $("brief-news");
    if (!data.news?.length) {
      news.append(element("p", "mc-muted", data.news ? "No major US releases listed for this session." : "Calendar data unavailable."));
    }
    for (const event of data.news || []) {
      const row = element("div", "mc-row");
      const time = event.instant
        ? element("time", "mnq-brief-time", localLabel.format(new Date(event.instant)))
        : element("span", "mnq-brief-time", "All day");
      if (event.instant) time.dateTime = event.instant;
      const copy = element("div", "mc-rt");
      copy.append(element("b", "", event.title));
      if (event.time_ny) copy.append(element("small", "", event.time_ny + " New York"));
      row.append(time, copy);
      news.append(row);
    }

    $("brief-state").hidden = true;
    $("brief-content").hidden = false;
  }

  const date = new URLSearchParams(location.search).get("date");
  async function load() {
    try {
      if (date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw Error("Invalid date");
      const response = await fetch("data/briefs/mnq/" + (date || "latest") + ".json", { cache: "no-cache" });
      if (!response.ok) throw Error("Brief unavailable");
      const data = await response.json();
      if (date && data.date !== date) throw Error("Unexpected brief date");
      render(data);
    } catch (error) {
      $("brief-state").textContent = date ? "This session brief is unavailable." : "The MNQ brief is temporarily unavailable.";
      $("brief-recovery").hidden = !date;
    }
  }
  load();
})();
