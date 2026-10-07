# Measured global session funnel (read-only public-data query)

The compiled `int_sessions` SQL was executed as a **capped read-only aggregate**, with its unbuilt staging view inlined. No BigQuery dataset, view, or table was created. The aggregate reconciled to the independent source profile for events, sessions, purchase events, and purchase-event USD revenue. Source: [metrics.json](metrics.json), `readonly_session_model_summary.row` and `profiling_summary`; dry-run estimate: [dry_runs.json](dry_runs.json), `readonly_session_summary.estimated_bytes`.

The session-conversion definition uses **all** modeled sessions: 4,848 purchase sessions / 360,129 sessions (`analysis.purchase_sessions`, `analysis.all_sessions`). The exact reduced fraction is `1616/120043` (`analysis.session_conversion`). Separately, 5,272 modeled sessions have no observed `session_start` event (`analysis.sessions_without_observed_session_start`), so the funnel-entry denominator is smaller than the session-conversion denominator.

| Cumulative step | Any-order sessions | Strict ordered sessions | `reports/metrics.json` key |
|---|---:|---:|---|
| session_start | 354,857 | 354,857 | `analysis.global_funnel[0]` |
| view_item | 75,271 | 74,974 | `analysis.global_funnel[1]` |
| add_to_cart | 14,897 | 14,043 | `analysis.global_funnel[2]` |
| begin_checkout | 5,868 | 5,080 | `analysis.global_funnel[3]` |
| purchase | 2,816 | 2,735 | `analysis.global_funnel[4]` |

Each row in `analysis.global_funnel` also stores both exact step-conversion fractions as numerator/denominator objects. Any-order reach means every earlier step event appeared somewhere in the same session. Strict reach requires each next event at a **later timestamp**; tied timestamps do not establish order. Both are cumulative distinct-session counts, not event counts. The gap between modes is therefore expected and is not a claim that the interface reports either total.

The specified new-user definition yields 332,837 sessions and 3,790 purchase sessions for users with a `first_visit` in the window (`analysis.user_cohorts[0]`). The complement has 27,292 sessions and 1,058 purchase sessions (`analysis.user_cohorts[1]`), labeled **no observed first_visit**, not confirmed returning. Exact conversion fractions for both cohorts are stored beside those counts in `analysis.user_cohorts`. Device and country results are in [funnel_segments.md](funnel_segments.md); the labeled revenue scenario is in [opportunity.md](opportunity.md). Product and category diagnostics are in [products.md](products.md), with the matching limitation made explicit.
