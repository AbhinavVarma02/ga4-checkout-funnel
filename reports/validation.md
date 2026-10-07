# Read-only daily reconciliation and five-session trace

Daily public-source totals and the compiled staging SELECT agree on events,
purchase events, and purchase-event USD revenue for every observed export day.
The dates and event/purchase counts also match the independent saved daily profile;
window revenue matches the saved source revenue total. Evidence:
`reports/metrics.json`, `readonly_daily_source.rows` (92 rows), compared with
`profiling.04_daily_profile.rows` and `profiling_summary.purchase_revenue_usd`.
This verifies the SELECT logic. Raw loading and materialized dbt relations remain
pending approval; this is not a source/raw pipeline gate result.

The five sessions use a fixed seed, hashing the two-field session key and choosing
the lowest hash within each disjoint diagnostic stratum. Strata take precedence
in this order: crosses export dates, any-order purchase without strict purchase,
strict purchase, missing session_start, other sessions. This is random selection
within diagnostic groups, not a representative sample or an error-rate estimate.
No original user/session identifiers are returned. The complete selected event
histories, model counts, sample hashes, eligible population counts, and verified
reach flags are under `readonly_session_traces.rows`. These small curated traces
are validation evidence; no bulk event export was downloaded.

I inspected the five histories against the model:

| Row / diagnostic group | Manual trace | Conclusion |
|---|---|---|
| 0: any_order_purchase_only | Start at 1610424284291014; view and cart both at 1610424345972334; checkout follows; purchase at 1610424589026658 for USD 37 | All five events exist. Strict reach stops at view because the sole cart ties that view. Any-order purchase true; strict purchase false. |
| 1: cross_midnight | Start and first view are dated 2021-01-14; another view is dated 2021-01-15 | One session assigned to 2021-01-14. Both modes reach view only; no purchase. |
| 2: missing_session_start | Four events on 2020-12-18 contain no session_start and no purchase | Retained in all-session counts. No cumulative funnel entry in either mode. |
| 3: other_sessions | Five events on 2021-01-12 include session_start and no view_item | Both modes reach session_start only; no purchase. |
| 4: strict_purchase | Start 1608152791670923 → view 1608152990334181 → cart 1608152998859066 → checkout 1608153344311299 → purchase 1608153570442826, USD 683 | A strictly increasing subsequence reaches all steps despite repeated and tied intervening events. |

Each row's full event count, earliest export date, purchase-event count, exact
purchase revenue sum, event-presence flags, and strictly ordered flags also passed
an independent Python reconstruction. Timestamp equality is never broken with
alphabetical event ordering to claim strict progress. Source keys for every number
in the trace table: `readonly_session_traces.rows[0]` through `[4]`, including
`event_trace`, `event_count`, `purchase_revenue_usd`, and verified reach arrays.

Both new queries were dry-run first, capped, and executed in US with billing
verified disabled. Estimated and actual processed/billed bytes and real job IDs
are saved under `readonly_daily_source` and `readonly_session_traces`; estimates
and execution status are also in `reports/dry_runs.json`. Billed bytes are query
metadata, not a dollar cost or a completed pipeline-run cost log.
