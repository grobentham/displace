(() => {
  const kind = document.body.dataset.tool;
  const status = document.getElementById("tool-status");
  const results = document.getElementById("tool-results");
  const isReplay = kind === "replay";
  const format = new Intl.DateTimeFormat(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: isReplay ? "America/New_York" : "UTC"
  });
  const path = isReplay ? "replay" : "exchange-hours";

  function row(item) {
    const node = document.createElement("li");
    const content = document.createElement("div");
    const label = document.createElement("strong");
    const detail = document.createElement("small");
    const date = format.format(new Date(isReplay ? item.at : item.date + "T12:00:00Z"));
    label.textContent = isReplay ? item.title : item.name;
    detail.textContent = isReplay ? date + " · " + item.at.slice(11, 16) + " New York" : date + " · " + item.hours;
    content.append(label, detail);
    node.append(content);
    if (isReplay) {
      const link = document.createElement("a");
      link.href = "backtest.html?release=" + encodeURIComponent(item.id);
      link.textContent = "Start replay";
      link.setAttribute("aria-label", "Start replay for " + item.title + " on " + date);
      node.append(link);
    }
    return node;
  }

  fetch("data/briefs/" + path + ".json", { cache: "no-cache" }).then(response => {
    if (!response.ok) throw Error("Snapshot unavailable");
    return response.json();
  }).then(data => {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const date = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const today = `${date.year}-${date.month}-${date.day}`;
    const items = isReplay ? data.releases : data.days.filter(day => day.date >= today);
    results.replaceChildren(...items.map(row));
    status.textContent = isReplay ? (items.length ? "Choose a release" : "There are no complete release windows available.") :
      items.length ? "Published schedule · " + data.asof : "No upcoming holiday hours in the published schedule.";
  }).catch(() => { status.textContent = isReplay ? "Release replays are temporarily unavailable." : "The schedule is temporarily unavailable."; });
})();
