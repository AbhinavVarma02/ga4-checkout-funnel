"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const ui = require("../../src/analysis/templates/prototype.js");
const metrics = JSON.parse(fs.readFileSync(path.join(__dirname, "../../reports/metrics.json"), "utf8"));
const data = metrics.local_prototype.payload;

test("exact fractions distinguish zero conversion from undefined", () => {
  assert.equal(ui.percent(null), "undefined");
  assert.equal(ui.percent({numerator: 0, denominator: 1}), "0.00%");
  assert.equal(ui.percent({numerator: 1, denominator: 4}), "25.00%");
});
test("mode switching uses independent cumulative counts and losses", () => {
  const view = data.views.all[0];
  assert.equal(ui.funnelRows(view, "any_order").at(-1).count, metrics.analysis.global_funnel.at(-1).any_order_sessions);
  assert.equal(ui.funnelRows(view, "strict_ordered").at(-1).count, metrics.analysis.global_funnel.at(-1).strict_ordered_sessions);
  assert.equal(ui.funnelRows(view, "any_order")[0].loss, metrics.analysis.worst_step_revenue_opportunity.lost_sessions);
});
test("table labels and category searches retain source labels safely", () => {
  assert.equal(ui.escapeHtml('<img onerror="x">'), "&lt;img onerror=&quot;x&quot;&gt;");
  assert.ok(!ui.table(["Category"], [["<script>x</script>"]]).includes("<script>"));
  const rows = [{item_category: "Original Apparel"}, {item_category: null}];
  assert.equal(ui.searchCategories(rows, "APPAREL").length, 1);
  assert.equal(ui.searchCategories(rows, "missing").length, 1);
});

function documentFixture() {
  const html = fs.readFileSync(path.join(__dirname, "../../src/analysis/templates/prototype.html"), "utf8");
  const nodes = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], {
    hidden: false, value: "", innerHTML: "", textContent: "", dataset: {}, handlers: {},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    setAttribute(key, value) { this[key] = value; }, focus() { this.focused = true; }
  }]));
  nodes["report-data"].textContent = JSON.stringify(data);
  nodes.dimension.value = "all";
  nodes.mode.value = "any_order";
  const tabs = ["funnel", "segments", "products", "opportunity"].map(page => {
    const tab = nodes["tab-" + page]; tab.dataset.page = page; return tab;
  });
  return {nodes, document: {getElementById: id => nodes[id], querySelectorAll: () => tabs}};
}

test("report initializes and all controls render source-backed results", () => {
  const {nodes, document} = documentFixture();
  ui.startReport(document);
  assert.ok(nodes.kpis.innerHTML.includes(data.views.all[0].all_sessions.toLocaleString("en-US")));
  assert.ok(!nodes["opportunity-count"].textContent.includes("NaN"));
  nodes.mode.value = "strict_ordered"; nodes.mode.handlers.change();
  assert.ok(nodes["funnel-table"].innerHTML.includes(metrics.analysis.global_funnel.at(-1).strict_ordered_sessions.toLocaleString("en-US")));
  nodes.dimension.value = "country"; nodes.dimension.handlers.change();
  nodes.segment.value = "1"; nodes.segment.handlers.change();
  assert.ok(nodes.scope.textContent.includes(data.views.country[1].label));
  assert.ok(nodes.kpis.innerHTML.includes(data.views.country[1].all_sessions.toLocaleString("en-US")));
  nodes["category-search"].value = "label that does not exist"; nodes["category-search"].handlers.input();
  assert.ok(nodes["category-table"].innerHTML.includes("No matching"));
  nodes.scenario.value = "2"; nodes.scenario.handlers.change();
  assert.equal(nodes["scenario-value"].textContent, Number(data.scenarios[2].incremental_revenue_usd_scenario_floor_cents).toLocaleString("en-US", {style: "currency", currency: "USD"}));
  nodes["tab-products"].handlers.click();
  assert.equal(nodes.filters.hidden, true);
  assert.equal(nodes["page-products"].hidden, false);
  assert.equal(nodes["page-funnel"].hidden, true);
  nodes["tab-products"].handlers.keydown({key: "Home", preventDefault() {}});
  assert.equal(nodes["page-funnel"].hidden, false);
  assert.equal(nodes["tab-funnel"].focused, true);
});
