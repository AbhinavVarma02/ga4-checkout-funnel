# P5.3 native one-day rerun: completed and verified

The owner's separate `go` authorized the exact first-day native build and two
snapshots in [rerun scope](replay_rerun_validation.md). The build exited 0 with **PASS=21**:
seven models and fourteen zero-failure data tests. The after snapshot exited 0
and matches the verified before snapshot exactly. All numbers, artifact hashes,
job IDs/SQL, parameters, recovery details and source keys are saved under
`warehouse_builds.p5_3_replay_rerun` in [metrics.json](metrics.json).

All three facts executed native insert_overwrite scripts. The actual completed
partition-selector job results each contain only **2020-11-01**. Each script
uses MERGE ON FALSE, deletes only selected start-date partitions, inserts the
complete temporary-table contents, and drops its dbt-created temporary table.
All three original fact creation timestamps remain unchanged; full refresh was
disabled. The three views and complete calendar were rebuilt as approved.
Final replay inventory contains exactly the seven expected relations, with no
temporary table remaining.

| Persisted relation | Identical before/after rows | Date coverage |
|---|---:|---|
| dim_date | 92 | 2020-11-01 to 2021-01-31 |
| fct_funnel_daily | 1,670 | 2020-11-01 to 2020-11-01 |
| fct_product_daily | 4,120 | 2020-11-01 to 2020-11-01 |
| fct_sessions | 2,625 | 2020-11-01 to 2020-11-01 |

For every relation, complete sorted row SHA-256 fingerprints, counts, date
ranges and non-null date checks are identical. Duplicate rows participate in
the fingerprints. The calendar has 92 distinct dates; each fact contains only
the first-day date. Independent keyed raw events and the session mart agree on
2,625 sessions, 14 purchase events, zero missing purchase revenues and **773 USD**
canonical purchase-event revenue. Raw contains 31,272 events. Item/funnel revenue
is not substituted for canonical purchase-event revenue.

The before SELECT succeeded, but its original local validator rejected the
lowercase hex emitted by BigQuery TO_HEX. Its original command exit was 1.
Corrected the overly strict uppercase regex without changing SQL and explicitly
disabled SDK job retry for supplied IDs. Metadata and the already completed
aggregate result were downloaded and revalidated; no second before SELECT was
submitted. All gates passed before the approved native build continued. The
original pending record and recovery are retained. Saved-result recovery also
preserves its recorded before comparison and cannot turn changed rows into a
successful equality claim.

| Executed scope | Non-SCRIPT jobs | Processed bytes | Billed bytes |
|---|---:|---:|---:|
| Native dbt build | 30 | 52,964,097 | 220,200,960 |
| Two snapshots | 2 | 17,654,876 | 104,857,600 |
| Approved total | 32 | 70,618,973 | 325,058,560 |

The complete inventory is 35 jobs: three SCRIPT parents plus 32 non-SCRIPT jobs.
The native build includes three view jobs, one calendar CTAS, three temporary
CTAS jobs, fourteen data-test SELECTs and nine script children (three partition
SELECTs, three MERGEs and three DROPs). Both snapshots are additional SELECTs.
Script parent totals equal their children's totals, so parents are excluded
from the byte sum. Default jobs.list returned 26 labeled root jobs; explicit
parent pagination supplied all nine children. Actual child caps are the parent's
remaining budget and never exceed the approved 128 MiB maximum. All jobs are
DONE without errors, in US, and reference only approved raw/replay datasets.

Gross query cost calculated from actual billed bytes is **$0.001847744** at the
recorded [Google rate](https://cloud.google.com/bigquery/pricing?authuser=1),
before allowances/credits. This is not an invoice or observed account spend;
account-wide allowance/spend remain unverified and storage is additional.
No byte-log SQL or CSV publication is included in this completed scope.

Metadata confirms raw and analyst inventories, schemas, view definitions,
expiration settings, creation/modification times, rows and bytes are unchanged.
Replay schemas, row/byte metadata, daily DATE partitioning, device/country
clustering and null expirations remain correct. Actual view SQL matches native
compiled SQL after removing leading comments/outer whitespace. All starting
metrics/dry-run values, all 300 Power BI file bytes/index/status, verified CSVs,
and offline report bytes are preserved. The after snapshot and native job records
are new evidence; canonical full-window analyst results are unchanged.

The final isolated current-source/tracked-Power-BI snapshot passes **173 Python
tests**, including nine new hash/recovery regressions. Python lint/format (63
files), snapshot SQL lint, five CSV provenance checks and mandatory wording
checks pass. This does not claim new Desktop rendering or remote CI. A local
streaming evidence write hit an unexpected AttributeError; atomic publication
kept the prior metrics intact and saved native artifacts were reused. A metadata
helper initially combined incompatible jobs.list flags and was corrected without
submitting a query. Neither incident caused a second cloud execution.

P5.3 is complete for implemented raw staging/incremental marts and a verified
native first-day rerun. The earlier native synthetic fixture covers multi-day
session/first_visit repair; broader loaded-history native behavior belongs to
future approved replay/backfill validation. No new raw date/load/rerun, Airflow
task/backfill, cost experiment, IAM/workflow, push or tag was executed.
The next native accounting SQL/CSV step requires its own bounded owner go.
