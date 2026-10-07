# Labeled revenue-opportunity scenario

The any-order, distinct-session funnel ranks `session_start → view_item` as the largest **modeled** revenue opportunity (`reports/metrics.json`, `analysis.dropoff_opportunities[0]`). It had 354,857 entering sessions, 75,271 continuing sessions, and 279,586 observed dropouts (`analysis.worst_step_revenue_opportunity`). Among the continuers, 4,602 sessions purchased and their purchase-event revenue was USD 343,240 (same key). The modeled downstream purchase rate is the exact fraction `4602/75271`; neither that rate nor the continued-session purchase value is an experimental treatment effect.

The scenario assumes some dropout sessions can be moved to a product view and then behave like the observed continuers. It applies only to the observed public-data window; it is **not annualized**, and it is not a forecast of real-company revenue. Exact rational calculations are stored in `analysis.worst_step_revenue_opportunity.all_dropouts_recovered_potential_usd_exact` and each `analysis.recovery_scenarios` row. Displayed dollars are floored to cents, never rounded up.

| Recovery assumption | Modeled incremental USD, floored to cents | `reports/metrics.json` key |
|---|---:|---|
| Recover 5% of observed dropouts | 63,746.39 | `analysis.recovery_scenarios[0]` |
| Recover 10% of observed dropouts | 127,492.79 | `analysis.recovery_scenarios[1]` |
| Recover 20% of observed dropouts | 254,985.58 | `analysis.recovery_scenarios[2]` |

One testable fix hypothesis is a clearer product-discovery call to action on entry pages. Desktop has the largest observed count of session-start-to-item-view dropouts, 162,086, followed by mobile at 111,280 (`analysis.by_device[0].dropoff_opportunities[0].lost_sessions` and `analysis.by_device[1].dropoff_opportunities[0].lost_sessions`). Those counts suggest where to inspect the experience first; they do **not** prove a UI defect or that these visitors intended to shop. An A/B test with eligible entry-page sessions and purchase-session conversion as the outcome would be needed to estimate causal lift. The public, obfuscated export has no such experiment.
