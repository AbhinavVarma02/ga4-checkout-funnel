# P5.6 first native Airflow integration

Status: **PASS**, completed under the owner's separate first-day `go` on
2026-10-05. The DAG is paused again. This closes Needs from human #15, while
controlled failure accounting and the full 92-day backfill remain separate gates.
The executed scope is retained in [the first-day gate](airflow_first_day_validation.md).
Source: `warehouse_builds.p5_6_first_airflow_run` in [metrics.json](metrics.json).

Airflow created backfill ID 1 for 2020-11-01 only, with reprocessing `none` and
maximum one active run. Run `backfill__2020-11-01T00:00:00+00:00`, label
`ga4_5f05b5f984a3facd2730de02`, completed successfully. All five actual task
instances (`extract_day`, `reconcile`, `dbt_build`, `log_bytes`, `finish`) passed
on their first attempt. Installed runtime, task logs, timestamps and hashes are
recorded in the source key; ignored originals are under
`reports/.checks/p5_6_first_day/`. The executed DAG source is the unchanged
runtime-validated source at `964e5ef`.

The extractor replaced only `ga4_raw.ga4_events$20201101`. The completed native
reconciliation result agrees on all eight signals: 31,272 events, 14 purchases,
773 USD purchase revenue, and zero observed transaction IDs on both sides.
Raw still has one partition and 23,503,520 logical bytes. Native dbt built seven
models and passed fourteen data tests with no failures, warnings or skips.
Its seven model SELECT preflights are saved in
[the run-specific dry-run artifact](dbt_dry_runs_ga4_5f05b5f984a3facd2730de02.json).

The actual CSV row matches exactly the independent completed-job API inventory:

| Accounting result | Actual value |
|---|---:|
| Non-SCRIPT jobs | 32 |
| Included script children | 9 |
| Excluded SCRIPT parent summaries | 3 |
| Processed bytes | 77,649,267 |
| Billed bytes | 265,289,728 |
| Failed query jobs | 0 |
| Separate logger lookup processed / billed bytes | 0 / 0 |

The lookup job is `4f0a3730-50c5-4db3-ac01-886140e69543`; its API reports zero
bytes and `cache_hit=false`. These are actual values for this lookup, not a
guarantee for later lookups. The CSV now has two rows and retains the previous
native accounting values. Its native byte length and SHA-256 are recorded in
metrics.json. Top-level queries have the approved 134,217,728-byte cap; script
children expose smaller remaining-budget caps, all positive and no larger than
their parent's cap, with actual billed bytes within those bounds. A local
collector's initial equal-cap assertion was corrected before evidence
publication; no query or task was repeated to recover that check.

At Google's checked reference rate of USD 6.25/TiB, the gross arithmetic is
USD 0.0015079975128173828125 before free allowance, credits and storage. The
first 1 TiB monthly query allowance is documented by
[Google BigQuery](https://cloud.google.com/bigquery) and its
[pricing page](https://cloud.google.com/bigquery/pricing?authuser=1).
Account-wide remaining allowance and spend are unknown; this is not an invoice.

Verification used the completed reconciliation/test artifacts and free job,
result and warehouse metadata APIs. Analyst metadata is unchanged. Raw/replay
inventory, schemas, row/byte metadata and expiration settings are preserved;
fact creation timestamps are unchanged. All three facts still have one daily
partition and device/country clustering. No additional paid snapshot SELECT ran.
The final script result sets are empty because the scripts end in cleanup;
explicit replacement arrays and full-row equality were **not rechecked** here.
Their earlier native proof remains [P5.3 evidence](replay_rerun_validation.md).
This run verifies its date/configuration/compiled filters and one-partition
metadata without claiming another full-row comparison.

All 300 owner Power BI files, their index/status, owner configuration, canonical
exports and offline report are preserved. There are no unrelated new query jobs
in the audited execution window. No other raw day, controlled failed run,
manual recovery, full-window backfill, IAM/workflow, push or tag was executed.
