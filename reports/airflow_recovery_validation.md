# P5.6: bounded native recovery verified

Owner go #17 completed one recovery of **2020-11-01** on 2026-10-06 UTC
(2026-10-05 in the owner's timezone). The DAG is **paused** again. All five tasks
succeeded with one new attempt each and no automatic retry. Seven dbt models
succeeded and fourteen native data tests passed with zero failures. This completes
the bounded failure/recovery validation; P5.6 still requires the separate full-window
cap/cost/allowance review and backfill go.

Source: `warehouse_builds.p5_6_airflow_recovery` in [metrics.json](metrics.json).
It contains actual before/after Airflow state, completed query IDs/SQL/caps/results,
metadata, task-log hashes, dbt results and artifact hashes. Ignored original logs
and dbt artifacts are under `reports/.checks/p5_6_recovery/`.

The installed non-partitioned backfill reused DagRun database ID 1 and
`backfill__2020-11-01T00:00:00+00:00`; backfill record 3 completed. Actual execution
start was `2026-10-06T00:04:42.948619+00:00`. The repaired query label is
`ga4_10c2704cac0623233d645387`, distinct from the historical executed label.
Counters advanced 2→3 for extraction/reconciliation/logging and 1→2 for dbt/finish.
No separate manual clear or second recovery submission occurred.

| Accounting | Query jobs | Processed bytes | Billed bytes |
|---|---:|---:|---:|
| Labelled leaf jobs | 32 | 77,649,267 | 265,289,728 |
| Separate logger lookup | 1 | 0 | 0 |

Thirty-five labelled records include three SCRIPT parent summaries and nine
children. The recorder excludes parents, includes children and matches the
independent job API inventory exactly. Every job completed successfully; the
128 MiB cap applied to top-level jobs, with inherited remaining child budgets.
The logger's actual dry-run estimate was also zero; the actual result still
contained all 32 jobs. These bytes describe jobs, not account spend or an invoice.

The native writer added a fourth [CSV row](bytes_billed.csv) using label/date/UTC
start identity. All three prior row dictionaries are unchanged, including their
recorded times and historical window markers. The writer sorts keys, so row
positions changed. The file remains native CRLF CSV.

Extraction replaced only the existing first-day raw partition. All eight real
source/raw signals match: 31,272 events, fourteen purchases and 773 USD revenue.
Raw remains one partition / 23,503,520 logical bytes. Replay has its same seven
relations; schemas, row/byte counts, partition/cluster/expiration metadata and
fact/raw creation times are preserved. Views/calendar were rebuilt as expected.
Analyst warehouse metadata is unchanged. All 300 owner Power BI file bytes,
index/status, owner configuration, canonical metrics/dry runs and exports are
preserved. Four local Airflow health components are healthy.

DAG source remains SHA-256
`2a2153e4cc7133fb58d0603d9278e22ce4c29fe8cf20fb9c4c041a2b0a694d67`,
matching serialized source. Current-source validation from the immediately prior
checkpoint is reused: 202 isolated tests with the documented allocator workaround,
79 related tests, fifteen SDK callback cases, native import and Python lint.
No implementation changed during this execution; these suites were not repeated.
Native execution verifies the repaired path against actual cloud results.

No extra paid snapshot/verification SELECT was submitted. Completed SCRIPT
results are empty after adapter cleanup; actual replacement arrays and full-row
equality were not rechecked. Earlier P5.3 equality evidence retains its scope.
Native failed-SQL billing, broader late-event repair, recurring operation,
P5.7 cost comparison, manual workflow/IAM, push and tag remain unclaimed.
