(() => {
  const local = new Intl.DateTimeFormat(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"
  });
  for (const time of document.querySelectorAll("time[data-local]")) {
    const date = new Date(time.dateTime);
    if (Number.isFinite(date.getTime())) time.textContent = local.format(date);
  }
})();
