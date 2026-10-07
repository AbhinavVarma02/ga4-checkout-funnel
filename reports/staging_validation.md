# Approved staging build and validation

The owner replied `go` to the exact two-view command in Needs from human #5.
The build succeeded in `ga4-checkout-funnel.ga4_analytics` in US with billing
disabled. It created only `stg_ga4_events` and `stg_ga4_items`; each is a logical
view with 17 columns. Both creation jobs report zero processed and billed bytes.
The dataset's automatic sandbox expiration was retained.

Catalog generation restricted to these two views also passed and includes their
actual column metadata. Its scope, schema checks, and metadata job bytes are
under `warehouse_builds.p2_2_staging.catalog`; the full dependent-model catalog
remains pending. dbt emitted a warning about an optional `table_owner` field,
while the command succeeded and all actual staging column names were present.

Source: [metrics.json](metrics.json), `warehouse_builds.p2_2_staging`, including
the exact command, build timestamp, actual schemas, view query hashes, expiration,
and creation job IDs. Heavy staging SELECTs were dry-run before creation; their
estimates are under `dbt_stg_ga4_events` and `dbt_stg_ga4_items` in
[dry_runs.json](dry_runs.json).

Read-only queries against the actual views were separately dry-run and capped.
Their saved rows, estimates, query IDs, and actual processed/billed bytes are
under `materialized_daily_source` and `materialized_staging_items`.

| Actual check | Result | Source key in metrics.json |
|---|---|---|
| Event/purchase counts and USD revenue by export date | Exact source agreement on all 92 dates | `materialized_daily_source.rows` |
| Staged event total | 4,295,584 | `warehouse_builds.p2_2_staging.verification.events` |
| Staged purchase events | 5,692 | `warehouse_builds.p2_2_staging.verification.purchase_events` |
| Item grain, missingness, and USD revenue by event name | Exact agreement with saved independent source profile | `materialized_staging_items.rows` versus `profiling.08_items_profile.rows` |
| Staged item rows | 3,982,732 across 8 event groups | `warehouse_builds.p2_2_staging.verification.item_rows` and `.item_event_groups` |
| Local Python tests | 68 pass, no failures/errors/skips | `warehouse_builds.p2_2_staging.verification.pytest` |

Python lint/format and the changed SQL lint pass. The validation CLI's default
inlined mode remains available; `--materialized-staging` uses only the staging
relations and retains separate evidence keys. Item comparisons reject coverage,
missingness, or revenue differences before publishing a successful result.

The staging build selected no dbt data or unit tests, so none are claimed as
executed. Intermediate/mart resource creation, dbt tests, raw loads, billing,
backfill, Power BI execution, remote CI, and owner review remain pending. No
approval for those actions is inferred from this successful staging build.
