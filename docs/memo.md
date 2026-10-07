# Decision memo: prioritize product discovery

**To:** Hypothetical Head of Ecommerce, Google Merchandise Store  
**Scope:** Public, obfuscated GA4 export, 2020-11-01 to 2021-01-31  
**Decision proposed:** Test a clearer “Shop products” call to action on eligible
entry pages, starting with a desktop experience review. This is a hypothesis for
an experiment, not a diagnosed UI defect or an implemented improvement.

The largest modeled opportunity is **session_start → view_item**: 354,857 entering
sessions, 75,271 continuing sessions, and 279,586 dropouts. Desktop accounts for
162,086 of these dropouts and mobile for 111,280. The United States has the largest
observed session base. Absolute losses guide where to inspect; they do not prove
shopping intent, device friction, or country-specific causes. Sources:
`reports/metrics.json`, `analysis.worst_step_revenue_opportunity`,
`analysis.by_device[0:2].dropoff_opportunities[0]`, `analysis.by_country[0]`.

Overall, 4,848 of 360,129 sessions purchased. Cumulative any-order reach falls from
354,857 session starts to 75,271 item views, 14,897 carts, 5,868 checkouts, and 2,816
purchases; strict chronological reach ends at 2,735 purchases. Overall purchase
conversion includes sessions that lack earlier funnel events. Any-order reach
requires all earlier events somewhere in the session; strict reach requires
increasing timestamps. Both assign midnight-spanning sessions to their first
observed export date. Sources: `analysis.all_sessions`, `analysis.purchase_sessions`,
`analysis.global_funnel`; [validation](../reports/validation.md).

**What could it be worth?** If 5%, 10%, or 20% of the observed entry-to-view dropouts
were recovered and behaved like existing view continuers, modeled incremental
purchase-event revenue would be **USD 63,746.39 / 127,492.79 / 254,985.58**, respectively,
for this historical window, floored to cents. Inputs use the continuers' observed
purchase rate and purchase-event revenue per continuing session. These are
assumed scenarios, not causal lift, a forecast, an annualized value, or net profit.
Source: `analysis.recovery_scenarios`; [calculation](../reports/opportunity.md).

Apparel leads observed item revenue, but product/category-key matching finds no
groups with both a view and purchase; product conversion cannot reliably rank
product-page fixes. Category reach deduplicates sessions directly and may involve
different products. Users with observed first_visit account for 332,837 sessions
and 3,790 purchase sessions; the complement has 27,292 sessions and 1,058 purchase
sessions, labeled “no observed first_visit,” not confirmed returning. Sources:
`product_analysis`, `analysis.user_cohorts`; [products](../reports/products.md).

**Next evidence:** Review entry-page behavior and tracking, then randomize eligible
sessions between the current experience and the clearer shopping action. Use
purchase-session conversion as the primary outcome, item-view reach as a diagnostic,
and revenue per eligible session as a secondary outcome. Check device balance,
tracking continuity, and checkout performance. Set the test duration, sample size,
and decision threshold from actual eligible traffic before launch. No experiment or
intervention has been deployed. The separate historical replay completed all 92 sample dates. The saved Power BI
CSV Import report has completed owner Desktop validation; its monetary screenshot
precision differences are [disclosed](../reports/powerbi_validation.md#monetary-presentation).
Use the canonical scenario amounts above. Daily staging/source SELECT totals and
five diagnostic session traces pass. Approved sandbox dbt data tests and synthetic
unit fixtures also passed (`warehouse_builds.p2_5_tests.data_tests`, `.results`);
the actual source/raw quality gate subsequently passed in the complete historical replay. Artifact
evidence: `powerbi_desktop_artifact`; [Power BI validation](../reports/powerbi_validation.md).

LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users

LIMIT: obfuscated sample data; some totals don't fully reconcile

LIMIT: channel results are first-touch unless session-level source exists in the data

LIMIT: the daily pipeline replays historical daily tables as a simulated feed
