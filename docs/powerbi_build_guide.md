# Power BI Desktop build guide

The source-controlled [Breadcrumb.pbip](../powerbi/Breadcrumb.pbip) prototype now
contains the CSV Import model, relationships, DAX measures, and the four pages.
The owner opens and validates it instead of constructing the report from scratch.
The pages are ordered **Summary**, **Funnel by device and country**, **Drop-off
revenue by step**, and **Product and category performance**. See the
[project README](../powerbi/README.md) for source structure and automated checks.
P4.2 is complete: repository-backed PBIX, four screenshots and owner Desktop
DAX/model/filter/interaction validation are evidenced in OWNER_HANDOFF.
Walkthrough: Removed by owner / Not required.

## Open the prepared project on Windows

Keep WSL Ubuntu running. Use regular Power BI Desktop, not the Report Server
edition. If listed in **File → Options and settings → Options → Preview features**,
enable **Power BI Project (.pbip) save option**, **Store reports using enhanced
metadata format (PBIR)**, and **Store semantic model using TMDL format**, then
restart Desktop. Feature names/availability depend on the installed version.

In Windows Explorer, open:

```text
\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\powerbi
```

Double-click `Breadcrumb.pbip`, or use Desktop **File → Open → Browse** to select:

```text
\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\powerbi\Breadcrumb.pbip
```

If file association is unavailable, use File → Open with the project file filter.
`Breadcrumb.Report\definition.pbir` is also a documented Desktop entry point.
Choose **Home → Refresh** to populate the initially empty Import model from the
five existing CSVs. The `ExportsFolder` parameter already contains:

```text
\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\exports
```

For a path error, verify that folder in Windows Explorer and correct the parameter
in **Transform data → Manage parameters**. Do not import incomplete `.bi_*.csv`
files or rerun cloud exports for this validation. If asked for a local-file privacy
level, Private is sufficient. No Google account or cloud connection is required.
The `.pbi` cache is intentionally untracked; its absence is expected before refresh.

Run `Breadcrumb.SemanticModel\DAXQueries\Validate verified exports.dax` in Desktop
**DAX query view** after refresh; open/copy it into a new query tab if necessary.
All numeric `Passed` values and all blank-guard columns should be TRUE. These
queries ignore report slicers, so also do the interactive checks below. The exact
save/screenshot instructions are in [Power BI validation](../reports/powerbi_validation.md).

Before building the `.pbix`, the verified results can be explored in the
independent [offline interactive report](../reports/prototype.html). On Windows,
open `\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\reports\prototype.html`
in a browser. It requires no service, cloud login, or Power BI installation.
Funnel and segment controls use saved device/country results; products and
scenarios use the complete historical window. Its control tests pass locally,
but browser appearance and the Power BI DAX/filter checks still need owner review.

The project definitions are prepared and externally parsed; no rendered Desktop
report, screenshot, or `.pbix` is claimed. DAX/Power Query execution and visual
behavior remain owner checks. The prototype uses **Import** mode. The following
connection/model instructions describe the implemented design and optional manual
repairs; they are not prerequisites to opening the project.

## Choose the data connection

**A — BigQuery marts, after approved builds.** In Get data, select Google BigQuery,
set the Billing Project ID explicitly to the project in your local environment,
and sign in with your Google account. That field chooses the job project; it is
not an instruction to enable billing. Select `ga4_analytics.fct_sessions`,
`fct_funnel_daily`, `fct_product_daily`, and `dim_date`. Choose Transform data,
then Import. The sandbox marts were verified under Human Step #9; this prototype
uses only the earlier verified CSVs and submits no warehouse query. Do not create
resources or change connections for Human Step #6. Connector behavior is documented by
[Microsoft](https://learn.microsoft.com/en-us/power-query/connectors/google-bigquery).
Use account sign-in rather than copying a service-account key into the report.
Power BI refresh submits queries; perform cloud reads only under the approved
sandbox allowance, or approved billing/cost scope after Phase 5. The connector
cannot apply this project's Python per-query byte cap. Avoid scheduled refresh
until the owner has approved its cost scope.

**B — Local CSVs, with no Windows cloud login.** The prepared read-only exporter
can execute compiled mart SELECTs with upstream SELECTs inlined, so no cloud
relation is required. It dry-runs each query, caps bytes, reconciles results before
publishing, and records provenance in `reports/metrics.json`. Existing verified
CSVs are already present and referenced by the prototype: do not rerun the exporter
for this task. The following commands are reference-only for a separately scoped
future refresh. Only execute while
billing is verified disabled or under an explicitly approved cost scope:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked dotenv run -- dbt compile --project-dir dbt --profiles-dir dbt --no-introspect
PYTHONMALLOC=malloc PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked python -m pipeline.export_bi
```

In Windows, Get data → Text/CSV → Transform data for each of the four named CSVs
under `\\wsl.localhost\Ubuntu\home\abhinav_varma\projects\ga4-checkout-funnel\exports`.
Rename queries to the file stem, preserving dbt names. Use UTF-8, comma delimiter,
quoted-field handling, and headers. The files are generated analytical exports,
not source-event downloads; they are ignored by Git. File status and checksums are
recorded under `bi_exports`; missing files are pending, not sample fixtures.
Never import `.bi_*.csv` files: they are incomplete attempt artifacts. An existing
CSV changed outside the exporter requires owner approval before replacement.
Microsoft documents the [Text/CSV import](https://learn.microsoft.com/en-us/power-query/connectors/text-csv).

For either option, also import `category_summary.csv` from the same folder as
`category_summary`. This is the measured full-window category rollup, separate
from product sums; do not substitute summed product reach.

## Types and relationships

The prototype already has explicit relationships and disables automatic date/time.
If making manual repairs, remove automatically inferred relationships first.
Set `session_start_date` and `date_day` to Date; flags to True/False; counts and
`ga_session_id` to Whole number; all IDs, dimensions, labels, and item names to
Text. Explicitly convert CSV flags from `true`/`false`; never use text comparisons
in DAX. Set USD fields to Fixed decimal number. Source metrics retain exact
BigQuery decimals; report values are presentation amounts. Do not trim or merge
original category labels. Do not remove duplicate fact rows in Power Query.

Create `dim_device` and `dim_country` as Power Query references of `fct_sessions`:
keep only the corresponding column and remove duplicates. Retain any blank
member and check uniqueness after load. Create active **one-to-many**, single
filter-direction relationships from each of these dimensions to all three fact
tables. Also connect `dim_date[date_day]` to each fact's `session_start_date` and
mark `dim_date` as the date table. Do not relate facts to each other or make
bidirectional relationships. See Microsoft's
[dimension/fact guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema).
Device and country dimensions use the session's earliest event, consistently
across all marts. Use dimension fields for slicers so all facts respond together.

Leave `category_summary` disconnected: it has no day, device, or country grain.
Create a disconnected Enter data table named `recovery_assumption` with a Decimal
number column `fraction` and rows `0.05`, `0.10`, `0.20`; format as Percentage.
All expressions from [measures.dax](../powerbi/measures.dax) are already installed,
with unchanged definitions and explicit formats. Supplementary exposure/name
measures are in [prototype_measures.dax](../powerbi/prototype_measures.dax).
Percentages use two decimal places, counts use integers, and USD uses currency.
Undefined rates must remain blank, not zero, as documented
for [DIVIDE](https://learn.microsoft.com/en-us/dax/divide-function-dax).

## Page 1 — Summary

Use date, device, and country dimension slicers. Add cards for Sessions, Purchase
Sessions, Session Conversion, and Purchase Revenue USD. Add a line chart with
`dim_date[date_day]` and Session Conversion. Add a table for the two cohort labels
from `fct_sessions[user_cohort]`, with Sessions, Purchase Sessions, and Session
Conversion. Display `no_observed_first_visit` as “No observed first_visit”; never
call it confirmed returning.

Add a single-select `fct_funnel_daily[funnel_mode]` slicer, default `any_order`.
Create a horizontal bar chart or matrix with `step_name`, sorted by `step_order`,
and Funnel Reached Sessions, Funnel Lost Sessions, and Next Step Conversion.
Label the conversion column “Next step / current step.” Both modes are cumulative
session reach. Funnel measures deliberately return blank without exactly one
mode and step; never sum reach across steps or modes. Hide matrix grand totals.
Explain strict timestamps and the distinction between overall purchase conversion
and complete funnel purchase reach in a visible text box. Disable cohort-table interactions with funnel visuals; the funnel mart has no cohort dimension.

## Page 2 — Funnel by device and country

Sync date/device/country slicers from page 1. Use `dim_device[device_category]` in
a matrix with Sessions, Purchase Sessions, Session Conversion, and Purchase
Revenue USD. Use `dim_country[country]` in a second matrix sorted by Sessions,
with the same measures; a Top N filter is a display filter, not a global subtotal.
Add a funnel matrix with device rows and step columns using one selected mode.
Do not use separate device or country columns from facts as slicers.

Label channel fields, if shown in a tooltip/table, **First-touch source / medium**.
A country or device difference is descriptive; do not label it a causal defect.
Check that clicking a segment filters the intended charts and that Top N totals
are not mistaken for all-country conversion.

## Page 3 — Drop-off revenue by step

The generated page also includes any-order loss and modeled-exposure bar charts
and a step table. Exposure assumes **100%** recovery and equals lost sessions ×
next-step continuers' purchase-event revenue ÷ next-step continuing sessions,
matching `analysis.dropoff_opportunities`. It is modeled exposure, not observed
lost sales. The final purchase row has no next step and must remain blank. These
visuals are fixed to any_order; clicking a step cannot change the entry scenario.

Sync date/device/country slicers from page 1 and add a single-select recovery
fraction slicer, default 5%. Add Entry Dropouts Any Order and Modeled Recovery USD
cards. Label the amount **Assumed incremental USD, observed window; not causal
lift or profit**. The scenario always uses the any-order entry-to-view transition;
mode and step selectors are not active here. If filters change, the scenario
recalculates from that segment's observed losses and continuer revenue; the
published memo's amounts refer to the full window.

Show the proposed clearer “Shop products” entry-page action, the assumption that
recovered dropouts behave like observed continuers, and purchase-session conversion
as the proposed experiment outcome. Add [memo](memo.md) and [opportunity report](../reports/opportunity.md)
links in accompanying notes. State that no experiment or real deployment occurred.
Include all four mandatory LIMIT lines from the README in a visible notes panel;
keep the hypothetical/public/obfuscated qualifier in every page footer.

## Page 4 — Product and category performance

Use a product table with `item_id`, `item_category`, Item Revenue USD,
Product Viewing Sessions, Product Purchase without View Sessions, and Product
View to Purchase Conversion. Include both ID and category: the group key is the
pair. Add item_name only as a First-value display field or tooltip, so varying
names do not split the group. Sort by revenue. Hide totals for product session reach; summing distinct
product-session counts overcounts people. Revenue is additive. Product names may
vary; item name is descriptive, not the relationship key.

Place a separate full-window category table using `category_summary[item_category]`,
Category Item Revenue USD Full Window, Category Viewing Sessions Full Window,
and Category Conversion Full Window. Clearly label **2020-11-01 to 2021-01-31,
all devices and countries**. Do not sync or show date/device/country slicers on
this page, and disable product-table interactions with the category table. The
category count is deduplicated directly within category; a view and purchase can
involve different products. Keep category totals blank for session measures.

Add the visible limitation: “No item/category groups have a matched view and
purchase in this sample. Missing/mismatched keys and obfuscation limit conversion
interpretation; this does not prove product pages never convert.” Item revenue is
a diagnostic and must not replace canonical purchase-event revenue.

## Validate before saving

Reset all filters to the complete source window. Compare values with
`reports/metrics.json`: Sessions `analysis.all_sessions`, Purchase Sessions
`analysis.purchase_sessions`, revenue `profiling_summary.purchase_revenue_usd`,
both funnel series `analysis.global_funnel`, cohort counts `analysis.user_cohorts`,
and device/country results `analysis.by_device` / `analysis.by_country`. Scenario
amounts must match `analysis.recovery_scenarios` at 5%, 10%, and 20% to cents.
Apparel category counts/revenue must match `product_analysis.categories[0]`.
Purchase-only product groups have undefined conversion; groups with views but no
matched purchases have zero. Never average precomputed conversion percentages.

Test date/device/country filters, blank/empty labels, zero denominators, and both
funnel modes. Confirm the category table stays full-window and no cohort selection
silently changes global funnel claims. Save locally as `powerbi/Breadcrumb.pbix`.
The four screenshots and saved PBIX are repository-backed; CSV Import and owner
Desktop verification are complete. Walkthrough: Removed by owner / Not required.
Exact owner-supplied Power BI Desktop version/build: **2.158.1177.0 64-bit**.
It is recorded in [versions.md](versions.md), completing P6.2.

LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users

LIMIT: obfuscated sample data; some totals don't fully reconcile

LIMIT: channel results are first-touch unless session-level source exists in the data

LIMIT: the daily pipeline replays historical daily tables as a simulated feed

If fetching fails after a query completed, use the `execution_job_id` saved under
`bi_export_<model>` in `reports/dry_runs.json` to resume without rerunning it:

```bash
PYTHONMALLOC=malloc PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked python -m pipeline.export_bi --model fct_product_daily --resume-job <job-id>
```

The exporter verifies that the job matches the compiled SELECT, fetches fixed
small offset ranges, and retries malformed JSON pages only a bounded number of
times before failing. It publishes no partial file. If a job's temporary result
has expired, a new capped query is needed under the same cost approval rules.

Verified export note: the product export completed with `PYTHONMALLOC=malloc`
after native client crashes and a malformed JSON page under the default allocator.
This is an observed workaround, not a confirmed root-cause diagnosis. The
interpreter and pinned dependencies were retained. Existing completed CSVs and
all prior metric sections were preserved.
