/* The plan is stored locally. Only first-party market data is used to configure contract sizes. */
(function () {
  "use strict";
  const form = document.getElementById("mc-plan-form");
  if (!form) return;

  const $ = id => document.getElementById(id);
  const symbols = { nq: ["MNQ", "NQ"], es: ["MES", "ES"], gold: ["MGC", "GC"] };
  const inputs = Object.fromEntries(["allowance", "budget", "stop", "qty", "cost"].map(key => [key, $("mc-" + key)]));
  const fields = $("mc-plan-fields");
  const fit = $("mc-plan-fit");
  const metrics = $("mc-plan-metrics");
  const status = $("mc-plan-status");
  const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  let session;

  function storageKey(market) {
    return "displace.session-plan.v1." + market;
  }

  function load(market) {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey(market)) || "null");
      return saved && typeof saved === "object" ? saved : null;
    } catch (error) {
      return null;
    }
  }

  function contractSize() {
    return form.elements["mc-size"].value;
  }

  function cents(input) {
    return Math.round(input.valueAsNumber * 100);
  }

  function calculate() {
    if (!session || Object.values(inputs).some(input => !input.validity.valid)) return null;
    const allowance = cents(inputs.allowance);
    const budget = cents(inputs.budget);
    const cost = inputs.cost.value === "" ? 0 : cents(inputs.cost);
    const pointValue = contractSize() === "mini" ? session.market.pv : session.market.micro;
    const unit = Math.ceil(inputs.stop.valueAsNumber * pointValue * 100 - 1e-8) + cost;
    const qty = inputs.qty.valueAsNumber;
    const total = qty * unit;
    if (unit <= 0 || ![allowance, budget, unit, total].every(Number.isSafeInteger)) return null;

    const max = Math.floor(Math.min(allowance, budget) / unit);
    return { unit, max, total, left: allowance - total, fits: qty <= max };
  }

  function render() {
    const result = calculate();
    metrics.hidden = !result;
    fit.classList.toggle("mc-warn", Boolean(result && !result.fits));
    if (!result) {
      const missing = ["allowance", "budget", "stop", "qty"].some(key => inputs[key].value === "");
      fit.textContent = missing
        ? "Enter your remaining allowance, trade risk budget and stop distance to check the trade."
        : "Check the amounts, stop distance and contract count.";
      return null;
    }

    $("mc-result-unit").textContent = dollars.format(result.unit / 100);
    $("mc-result-max").textContent = result.max.toLocaleString("en-US");
    $("mc-result-total").textContent = dollars.format(result.total / 100);
    $("mc-result-left").textContent = dollars.format(result.left / 100);
    fit.textContent = result.fits ? "Planned size fits your entered limits." : "Planned size exceeds at least one entered limit.";
    return result;
  }

  function setMarket(key, market, day, dateLabel) {
    if (session && session.key === key && session.day === day) return;
    session = { key, market, day, dateLabel };
    const saved = load(key);
    const sameDay = Boolean(saved && saved.day === day);
    form.elements["mc-size"].value = saved && saved.size === "mini" ? "mini" : "micro";
    $("mc-sym-micro").textContent = symbols[key][0];
    $("mc-sym-mini").textContent = symbols[key][1];
    $("mc-plan-session").textContent = market.name + " · " + dateLabel + " session";

    inputs.allowance.value = sameDay ? saved.allowance : "";
    inputs.stop.value = sameDay ? saved.stop : "";
    inputs.qty.value = sameDay ? saved.qty : "1";
    inputs.budget.value = saved?.budget ?? "";
    inputs.cost.value = saved?.cost ?? "";
    fields.disabled = false;
    status.textContent = sameDay ? "Saved plan loaded from this device." : "";
    $("mc-plan-link").textContent = sameDay ? "Review my session plan" : "Plan my session";
    $("mc-calendar-feed").hidden = !sameDay;
    render();
  }

  form.addEventListener("input", event => {
    if (event.target.name === "mc-size") inputs.cost.value = "";
    status.textContent = "";
    render();
  });

  form.addEventListener("submit", event => {
    event.preventDefault();
    if (!render()) return;
    const plan = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value]));
    Object.assign(plan, { day: session.day, size: contractSize() });
    try {
      localStorage.setItem(storageKey(session.key), JSON.stringify(plan));
      status.textContent = "Plan saved on this device for " + session.dateLabel + ".";
      $("mc-plan-link").textContent = "Review my session plan";
      $("mc-calendar-feed").hidden = false;
    } catch (error) {
      status.textContent = "This browser could not save the plan.";
    }
  });

  window.DisplaceSessionPlanner = { setMarket };
})();
