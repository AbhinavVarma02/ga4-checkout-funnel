"use strict";

function escapeHtml(value) {
  return String(value ?? "(missing)").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}
const number = value => Number(value).toLocaleString("en-US");
const money = value => Number(value).toLocaleString("en-US", {style: "currency", currency: "USD", minimumFractionDigits: 2});
function percent(fraction) {
  return fraction === null ? "undefined" : (100 * fraction.numerator / fraction.denominator).toFixed(2) + "%";
}
function funnelRows(view, mode) {
  const countKey = mode === "any_order" ? "any_order_sessions" : "strict_ordered_sessions";
  const conversionKey = mode === "any_order" ? "any_order_step_conversion" : "strict_step_conversion";
  const lossKey = mode + "_dropoff_sessions";
  return view.global_funnel.map(step => ({
    name: step.step_name, count: step[countKey], conversion: step[conversionKey], loss: step[lossKey]
  }));
}
function table(headers, rows) {
  return "<table><thead><tr>" + headers.map((name, index) => `<th scope="col" class="${index ? "num" : ""}">${escapeHtml(name)}</th>`).join("") +
    "</tr></thead><tbody>" + rows.map(row => "<tr>" + row.map((value, index) => `<td class="${index ? "num" : ""}">${escapeHtml(value)}</td>`).join("") + "</tr>").join("") + "</tbody></table>";
}
function searchCategories(rows, query) {
  const text = query.trim().toLocaleLowerCase("en-US");
  return rows.filter(row => String(row.item_category ?? "(missing)").toLocaleLowerCase("en-US").includes(text));
}
function selectedView(data, dimension, index) {
  return data.views[dimension][index];
}

function startReport(document) {
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const el = id => document.getElementById(id);
  function updateSegments() {
    const dimension = el("dimension").value;
    el("segment-label").hidden = dimension === "all";
    el("segment").innerHTML = data.views[dimension].map((view, index) => `<option value="${index}">${escapeHtml(view.label)}</option>`).join("");
    el("segment").value = "0";
  }
  function render() {
    const dimension = el("dimension").value;
    const mode = el("mode").value;
    const view = selectedView(data, dimension, Number(el("segment").value));
    const steps = funnelRows(view, mode);
    el("scope").textContent = `${view.label} · Full historical window. Product and scenario pages always show all sessions.`;
    el("status").textContent = `${view.label}; ${mode === "any_order" ? "any-order" : "strict ordered"} funnel.`;
    const kpis = [
      ["Sessions", number(view.all_sessions), "User + session ID pair"],
      ["Purchase conversion", percent(view.session_conversion), `${number(view.purchase_sessions)} purchase sessions / all sessions`],
      ["Purchase-event revenue", money(view.purchase_revenue_usd), "USD · canonical project revenue"],
      ["Complete funnel purchases", number(steps.at(-1).count), "Cumulative reach in the selected mode"]
    ];
    el("kpis").innerHTML = kpis.map(([label, value, detail]) => `<article class="kpi"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div><div class="detail">${escapeHtml(detail)}</div></article>`).join("");
    el("mode-note").textContent = mode === "any_order" ? "Each step requires all preceding event names anywhere in the session. It does not establish event order." : "Each transition requires a strictly later timestamp. Tied timestamps do not prove order; later repeated events can establish progress.";
    const entry = steps[0].count;
    el("funnel-bars").innerHTML = steps.map(step => `<div><div class="bar-top"><span>${escapeHtml(step.name.replaceAll("_", " "))}</span><strong>${number(step.count)}</strong></div><div class="track" aria-hidden="true"><div class="fill" style="width:${entry ? 100 * step.count / entry : 0}%"></div></div></div>`).join("");
    el("funnel-table").innerHTML = table(["Step", "Sessions", "From prior step", "Lost to next"], steps.map((step, index) => [step.name, number(step.count), index ? percent(step.conversion) : "Entry", step.loss === null ? "—" : number(step.loss)]));
    el("cohort-table").innerHTML = table(["Cohort", "Sessions", "Purchases", "Conversion"], view.user_cohorts.map(row => [row.cohort === "new_in_window" ? "Observed first_visit" : "No observed first_visit", number(row.sessions), number(row.purchase_sessions), percent(row.session_conversion)]));
    el("missing-start").textContent = `${number(view.sessions_without_observed_session_start)} sessions have no observed session_start. They remain in overall conversion; cumulative funnel reach excludes them.`;
    const comparison = dimension === "all" ? data.views.device : data.views[dimension];
    el("segment-table").innerHTML = table([dimension === "country" ? "Country" : "Device", "Sessions", "Purchase conversion", "Complete funnel", "Purchase revenue"], comparison.map(row => [row.label + (dimension !== "all" && row === view ? " · selected" : ""), number(row.all_sessions), percent(row.session_conversion), number(funnelRows(row, mode).at(-1).count), money(row.purchase_revenue_usd)]));
  }
  function renderCategories() {
    const rows = searchCategories(data.categories, el("category-search").value);
    el("category-table").innerHTML = rows.length ? table(["Category", "Views", "Purchases", "Both", "Without view", "Item revenue", "Both / views"], rows.map(row => [row.item_category, number(row.viewing_sessions), number(row.purchasing_sessions), number(row.view_and_purchase_sessions), number(row.purchase_without_view_sessions), money(row.purchase_item_revenue_usd), percent(row.view_to_purchase_conversion)])) : '<p class="note">No matching category labels.</p>';
  }
  function renderScenario() {
    const scenario = data.scenarios[Number(el("scenario").value)];
    el("scenario-value").textContent = money(scenario.incremental_revenue_usd_scenario_floor_cents);
  }
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function activate(tab) {
    for (const button of tabs) {
      const selected = button === tab;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      el("page-" + button.dataset.page).hidden = !selected;
    }
    el("filters").hidden = ["products", "opportunity"].includes(tab.dataset.page);
    el("status").hidden = el("filters").hidden;
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", event => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); activate(tabs[next]); tabs[next].focus(); }
    });
  });
  el("dimension").addEventListener("change", () => { updateSegments(); render(); });
  el("segment").addEventListener("change", render);
  el("mode").addEventListener("change", render);
  el("category-search").addEventListener("input", renderCategories);
  el("scenario").addEventListener("change", renderScenario);
  el("scenario").innerHTML = data.scenarios.map((scenario, index) => `<option value="${index}">${escapeHtml(scenario.label)}</option>`).join("");
  el("scenario").value = "0";
  el("opportunity-step").textContent = `${data.worst_opportunity.from_step} → ${data.worst_opportunity.to_step}`;
  el("opportunity-count").textContent = `${number(data.worst_opportunity.lost_sessions)} sessions did not reach the next cumulative any-order step. This is the largest modeled revenue opportunity.`;
  el("product-limit").textContent = `${number(data.product_matching_groups)} item/category groups have a matched view and purchase. Treat this as an observed matching limitation, not evidence that product pages never convert.`;
  el("product-table").innerHTML = table(["Product", "Item ID", "Category", "Views", "Without view", "Item revenue"], data.products.map(row => [row.item_name, row.item_id, row.item_category, number(row.viewing_sessions), number(row.purchase_without_view_sessions), money(row.purchase_item_revenue_usd)]));
  el("revenue-gap").textContent = `${money(data.profile.purchase_revenue_usd)} purchase-event revenue versus ${money(data.profile.purchase_item_revenue_usd)} item revenue: ${money(data.profile.event_minus_item_revenue_usd)} gap.`;
  updateSegments(); render(); renderCategories(); renderScenario();
}

if (typeof module !== "undefined") module.exports = {escapeHtml, percent, funnelRows, table, searchCategories, selectedView, startReport};
if (typeof document !== "undefined") startReport(document);
