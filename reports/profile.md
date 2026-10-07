# Real-data profile of the public GA4 export

All figures below are from BigQuery queries against the public daily tables for 2020-11-01 through 2021-01-31. The project had billing disabled when these read-only queries ran. Each query was dry-run first; its estimate and executed job ID are recorded in [dry_runs.json](dry_runs.json) and [metrics.json](metrics.json). The figures describe the obfuscated export, not the GA4 interface or a real company's results.

## Daily activity and session grain

| Observed measure | Value | `reports/metrics.json` key |
|---|---:|---|
| Days with daily profile rows | 92 | `profiling_summary.observed_days` |
| Events | 4,295,584 | `profiling_summary.events` |
| Minimum daily events | 21,355 | `profiling_summary.minimum_daily_events` |
| Maximum daily events | 92,199 | `profiling_summary.maximum_daily_events` |
| Sessions assigned to first observed event date | 360,129 | `profiling_summary.observed_sessions` |
| Sessions observed on more than one export date | 845 | `profiling_summary.cross_midnight_sessions` |
| Sum of distinct sessions counted separately on each export date | 360,974 | `profiling_summary.daily_observed_session_sum` |
| Extra date-session occurrences from summing daily distinct counts | 845 | `profiling_summary.extra_day_session_occurrences` |
| `first_visit` events | 257,462 | `profiling_summary.first_visit_events` |
| Purchase events | 5,692 | `profiling_summary.purchase_events` |

The complete **per-day** `event_count`, `user_count`, `observed_session_count`, `first_visit_events`, and `purchase_events` are in `profiling.04_daily_profile.rows`. Its `user_count` is distinct within a date and must not be summed as a window-level unique-user count. The canonical daily session count and cross-midnight count, assigned to each session's first observed event date, are in `profiling.06_midnight_sessions.rows`. Summing export-date session counts double-counts the cross-midnight sessions shown above; the session mart must use the canonical start date.

## Ecommerce event coverage

| Event | Event count | Active dates | `reports/metrics.json` key |
|---|---:|---:|---|
| view_item | 386,068 | 92 | `profiling.02_event_names.rows` (`view_item`) |
| add_to_cart | 58,543 | 74 | `profiling.02_event_names.rows` (`add_to_cart`) |
| begin_checkout | 38,757 | 92 | `profiling.02_event_names.rows` (`begin_checkout`) |
| add_shipping_info | 19,722 | 92 | `profiling.02_event_names.rows` (`add_shipping_info`) |
| add_payment_info | 13,899 | 92 | `profiling.02_event_names.rows` (`add_payment_info`) |
| purchase | 5,692 | 92 | `profiling.02_event_names.rows` (`purchase`) |

The **per-day** event counts, item-row counts, revenue sums, and transaction/revenue null counts for these ecommerce events are in `profiling.05_commerce_profile.rows`. A missing event type on a date is not silently filled with a measured zero in that query. `add_to_cart` is absent on some dates, so funnel comparisons need an explicit missing-step caveat.

## Missingness and purchase identifiers

| Check | Observed result | `reports/metrics.json` key |
|---|---:|---|
| Events missing `user_pseudo_id` | 0 / 4,295,584 | `profiling_summary.null_user_id_events`, `profiling_summary.events` |
| Events missing `ga_session_id` | 0 / 4,295,584 | `profiling_summary.null_session_id_events`, `profiling_summary.events` |
| Purchase events missing `ecommerce.purchase_revenue` | 450 / 5,692 | `profiling_summary.null_purchase_revenue_events`, `profiling_summary.purchase_events` |
| Purchase events missing `ecommerce.purchase_revenue_in_usd` | 0 / 5,692 | `profiling_summary.null_purchase_revenue_usd_events`, `profiling_summary.purchase_events` |
| Purchase item rows missing `item_revenue_in_usd` | 448 / 16,003 | `profiling_summary.null_item_revenue_rows`, `profiling.10_revenue_reconciliation.rows[0].purchase_item_rows` |
| Purchase events with missing or blank transaction ID | 23 / 5,692 | `profiling_summary.missing_or_blank_transaction_ids`, `profiling_summary.purchase_events` |
| Distinct nonblank transaction IDs | 4,452 | `profiling_summary.distinct_nonblank_transaction_ids` |
| Transaction IDs used by multiple purchase events | 327 | `profiling_summary.repeated_transaction_ids` |

`profiling.07_purchase_ids.rows` gives the per-day purchase-event, null-ID, and distinct-ID counts. `profiling.11_purchase_id_reconciliation.rows[0]` checks IDs across the whole window. Purchase events, purchase sessions, and distinct transaction IDs are different metrics; the duplicated and missing IDs make that distinction material.

## Purchase versus item revenue

| Measure | Observed USD value | `reports/metrics.json` key |
|---|---:|---|
| Purchase-event revenue (`ecommerce.purchase_revenue_in_usd`) | 362,165 | `profiling_summary.purchase_revenue_usd` |
| Purchase-item revenue (`items.item_revenue_in_usd`) | 362,110 | `profiling_summary.purchase_item_revenue_usd` |
| Event minus item revenue, net gap | 55 | `profiling_summary.event_minus_item_revenue_usd` |

At the individual purchase-event grain, 1,001 events have unequal event-level and summed item-level USD revenue (`profiling_summary.purchase_events_with_revenue_gap`). The net gap does not describe the magnitude or direction of each event-level difference. The BigQuery source fields are `FLOAT64`; the reconciliation query casts observed values to `BIGNUMERIC` before summing. These are observed source inconsistencies, not a pipeline correction. The cause of each difference is not proven; the export is obfuscated. Use purchase-event USD revenue as the project revenue measure and show the item gap rather than forcing item totals to match.

## Dry-run record

All executed P1.3 queries had a successful preceding dry run and a per-query maximum-bytes-billed cap. Exact estimates are in `reports/dry_runs.json` under each query's `estimated_bytes` key: `04_daily_profile`, `05_commerce_profile`, `06_midnight_sessions`, `07_purchase_ids`, `10_revenue_reconciliation`, and `11_purchase_id_reconciliation`. The largest estimate among them was 1,099,665,202 bytes for `05_commerce_profile` (`05_commerce_profile.estimated_bytes`). Estimates are processed bytes, not billed bytes or a currency cost. One local client process exited unexpectedly after a successful `06_midnight_sessions` dry run; the read-only query was retried, completed, and its result saved. No cloud table or dataset was written.
