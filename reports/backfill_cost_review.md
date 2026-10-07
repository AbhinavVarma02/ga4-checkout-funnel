# P5.6: full-window cap and cost preparation

Status: **prepared, execution blocked at separate owner gate #18**.
[Exact gate](airflow_gate23_validation.md), [source-keyed output](metrics.json)
(`continuation_validation.p5_6_full_window_preparation`) and
[machine-readable plan](backfill_cost_preflight.json) record actual planning
output and its limits. Current runtime stays **paused / 128 MiB**; the proposed
[4 GiB environment](../airflow/backfill.env.example) is not activated.

The current installed CLI dry run, using reprocess-behavior none and explicit
false diagnostic flag, now lists **91 eligible dates: 2020-11-02–2021-01-31**.
It skips the successful first-day run. Read-only metadata confirms one DagRun,
five task instances and three completed backfill records; planning created none.
This is an eligibility check after recovery, not a repeated date-mapping proof.

The completed 92-day extraction plan is reused, not rerun: 3,583,657,854 source
scan bytes for all days, **3,560,091,790** for the remaining 91; maximum day
79,162,796. Saved representative model SELECT dry runs are also reused.

| History through | Seven model SELECT estimate sum | Largest model SELECT estimate |
|---|---:|---:|
| 2020-11-01, actual loaded raw | 64,727,777 | 18,469,665 |
| 2020-11-07, public equivalent | 698,379,484 | 202,176,912 |
| 2020-11-30, public equivalent | 3,190,478,710 | 941,420,041 |
| 2021-01-31, public equivalent | 9,495,090,030 | 2,891,550,912 |

Later history exceeds 128 MiB. The proposed **4,294,967,296-byte (4 GiB)** cap
fits every saved SELECT estimate. Seven model SELECT preflights are validated
queries, not seven charged materializations: views and generated DML behave
differently, and downstream models may read materialized facts rather than
fully inlined source history.

Fourteen new dry runs fill the final-history test-planning gap without repeating
first-day tests. Compiled source matches current repository models. View tests
inline the DATE-converted public export through January 31; fact tests use the
unchanged, already populated full-window analyst tables as proxies. Their SELECT
estimates sum **4,196,060,548 bytes**, maximum **1,038,149,379**, all below 4 GiB.
No tests executed, no result pass is claimed, and these proxies do not establish
future replay table bytes. Query/mutation guards allow dry runs only.

An explicitly flat reference scenario applies the final-history three fact
SELECT estimates plus those final-history test proxies to each of 91 days and
adds remaining extraction scanning. Code produces **733,058,253,819 estimated
processed bytes / 0.666713 TiB**, about **$4.17 gross** before free allowance,
billing rounding and omitted work. This is arithmetic for review, not a
whole-pipeline forecast, upper bound or measured cost. It does not model
history growth, reconciliation, generated scripts/DML/adapter metadata,
client/adapter/task retries or temporary/persistent/time-travel storage.

The [official BigQuery pricing page](https://cloud.google.com/bigquery/pricing?authuser=1),
checked 2026-10-06 UTC, lists US on-demand queries at $6.25/TiB after the monthly
1 TiB account allowance and 10 GiB free storage. Active logical storage is listed
at $0.000031507/GiB-hour. A single 4 GiB capped query corresponds to $0.024414
gross query pricing. Billing is enabled; remaining account-wide query/storage
allowance, spend, trial credit and other use are unknown. These calculations do
not establish an invoice or free execution.

[Google's script dry-run documentation](https://docs.cloud.google.com/bigquery/docs/multi-statement-queries#dry-run_a_multi-statement_query)
explains why a generated-script total is not supplied: DDL/control flow can stop
validation and future temporary table contents are absent. First-day actual
scripts/results remain archived: three parents, nine children, 32 leaf jobs and
265,289,728 billed bytes, with a separate zero-byte lookup. Future scripts must
retain the approved cap; cap failures require stopping rather than raising it.

The operating scope observes job APIs and per-day CSV accounting, preserves
previous records, and pauses at any observed unexpected failure or at **512 GiB
of cumulative completed job billing** for the new backfill, including lookup
jobs. This is a monitoring checkpoint, not a server-enforced aggregate budget;
already active work may complete after pause. No quota, billing or IAM setting
is changed. A checkpoint reached before all 91 dates finish leaves P5.6 partial
and requires a separately reviewed continuation go.

All existing evidence, owner configuration/Power BI files and current runtime
cap are preserved. No real backfill, raw load, model/test execution, CSV row,
paid verification SELECT, cost comparison, IAM/workflow, push or tag occurred
in this preparation.
