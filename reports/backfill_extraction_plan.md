# P5.6 extraction planning: all 92 source dates dry-run only

Planning covers the immutable sample from 2020-11-01 through 2021-01-31, with
one physical public source SELECT per day and the source date converted to DATE.
The unchanged first-day estimate from completed P5.2 preparation was reused;
**91 additional days** were dry-run through the current extractor with native
query submission intercepted to require `dry_run=True` and US location.
No executed SELECT, load, partition overwrite, resource creation or Airflow action
occurred. This preparation does not authorize a backfill.

All 92 estimates are known and nonnegative, and fit the **134,217,728-byte
(128 MiB) per-day planning cap**. Total estimated source scan is
**3,583,657,854 bytes**; the largest day estimates **79,162,796 bytes**.
Every date's real estimate, exact SQL, SHA-256 and dry-run/reuse provenance is
saved in `warehouse_builds.p5_6_backfill_extraction_plan` in
[metrics.json](metrics.json) and `backfill_extraction_plan` in
[dry_runs.json](dry_runs.json). Pre-existing dry-run and analyst evidence values
are preserved.

This is extraction-source scanning only. Reconciliation, native dbt scripts/
DML/tests, byte logging, retries and storage are additional and are not estimated
by this plan. A future full-window backfill would also replace the already loaded
first-day partition and requires explicit scope review and a separate owner go.
No whole-pipeline price, account-wide remaining allowance, production deployment,
or partition cost saving is claimed.

Current [edited-DAG runtime validation](airflow_runtime_validation.md) now passes
and Needs from human #13 is complete. The DAG remains paused with automatic catchup
disabled. Scheduling, a controlled failed run, broader native loaded-history
repair, failed-run accounting and the actual 92-day backfill remain incomplete.
The later separately approved [P5.5 byte-log SELECT/CSV](bytes_log_validation.md)
is now complete. The healthy paused runtime has no DAG runs; any later cloud
task/backfill retains its own scoped go.
Completed P5.5 approval authorizes none of those later actions.

## Subsequent full-window preparation

Bounded first-day integration/failure/recovery have since completed. Current reprocess-none planning skips the successful first-day run, so the [next #18 scope](airflow_gate23_validation.md) has 91 additional raw dates within the 92-day window. The extraction estimates above are reused, not repeated. [Cost review](backfill_cost_review.md) and continuation_validation.p5_6_full_window_preparation cover later planning and limitations; no full-window execution is authorized or claimed.
