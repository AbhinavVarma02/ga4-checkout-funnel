# P5.3 initial replay execution validation

The owner's separate `go` authorized the exact isolated first-build command in
[replay initialization](replay_initialization_validation.md), including creation of US
`ga4-checkout-funnel.ga4_replay_analytics`. The command exited 0 with
**PASS=21, ERROR=0, WARN=0, SKIP=0**. Seven models and fourteen native data tests
completed; every test reported zero failures. Synthetic units were excluded.
The pinned versions were dbt Core 1.12.5 and dbt-bigquery 1.12.1.

All published numbers and actual source/job/artifact keys are saved under
`warehouse_builds.p5_3_replay_initialization` in [metrics.json](metrics.json).
The pre-execution native SELECT preflight was refreshed successfully at the
same first-day raw checkpoint; estimates remained 174,986,425 bytes. Billing
was enabled, as previously approved; no billing setting was changed.

| New relation | Type | Metadata rows | Logical bytes |
|---|---|---:|---:|
| dim_date | TABLE | 92 | 3,680 |
| fct_funnel_daily | TABLE | 1,670 | 189,781 |
| fct_product_daily | TABLE | 4,120 | 602,806 |
| fct_sessions | TABLE | 2,625 | 540,190 |
| int_sessions | VIEW | 0 | 0 |
| stg_ga4_events | VIEW | 0 | 0 |
| stg_ga4_items | VIEW | 0 | 0 |

Views have zero storage/row metadata; their business row counts were not queried.
These facts contain the currently loaded first-day history, not the complete
analyst window. All three fact tables use daily DATE `session_start_date`
partitioning and `device_category, country` clustering. Dataset, relation and
partition expirations are absent. `dim_date` is a plain table. Full refresh is
disabled in the native manifest. The first build created facts through CTAS;
it did not execute native insert_overwrite.

All 118 named/ordered columns match the analyst schema except the explicit,
expected `stg_ga4_events.event_date_raw` STRING → DATE change: replay reads the
already converted native raw date. All three actual view definitions match
native compiled SQL after trimming outer whitespace and leading line comments;
BigQuery dropped the leading `int_sessions` comment. No SQL expression was
normalized away. Table schema and partition metadata were checked through APIs.

The complete labeled job inventory contains **22** jobs: one CREATE_SCHEMA,
three CREATE_VIEW, four CREATE_TABLE_AS_SELECT and fourteen SELECT data tests.
The extra schema job belongs to the native adapter, reports zero bytes, and
creates only the expressly approved dataset. Every job is DONE without errors,
in US, with the approved 134,217,728-byte cap and matching dbt invocation/run
labels. Actual SQL hashes, job IDs, destinations, dependencies and byte totals
are retained. No public dataset was read by the build. All referenced persistent
relations belong to the approved raw or isolated replay datasets.

Total processed bytes: **42,740,354**. Total billed bytes: **115,343,360**.
At the recorded [Google on-demand rate](https://cloud.google.com/bigquery/pricing?authuser=1)
of $6.25/TiB, the gross calculation is **$0.0006556511**, before free allowance
or credits. This is not an invoice or observed account spend. New logical table
storage is 1,336,457 bytes; storage billing is additional. Account-wide remaining
allowance/spend remain unverified. The initial 21-node cap planning sum excluded
the zero-byte schema DDL and is not a project budget.

Before/after metadata comparisons establish that existing raw and analyst
relations, schemas, view definitions, creation/modification timestamps,
expirations, rows and bytes are unchanged. The expected isolated dataset is the
only dataset inventory addition. No native rerun, new raw date/load, extra data
SELECT, new catalog/unit run, Airflow task/backfill, byte-log SELECT, cost
comparison, IAM change or workflow execution occurred.

The REST table metadata did not expose `numPartitions`. No populated fact
partition count or independently queried date coverage is claimed. The initial
fourteen native tests do not by themselves establish source/replay aggregate
reconciliation, identical before/after rows, multi-day lookback or full calendar
values. Those claims were pending at this initial-build checkpoint; the later
bounded native rerun now verifies them as recorded below.

The later separate owner-go [first-day rerun](replay_rerun_validation.md) is now
complete with capped before/after aggregate snapshots. That scope was separately approved;
further executed snapshots or partition replacement require a new explicit `go`
under [runbook](../docs/runbook.md). No new raw date or Airflow operation is included.
