# P5.9: approved manual BigQuery execution

**P5.9 native execution and validation are complete.** The owner gave `go` for
the [literal reviewed-SHA gate](manual_workflow_native_validation.md). Exactly one dispatch
created [run 37557732932](https://github.com/AbhinavVarma02/ga4-checkout-funnel/actions/runs/37557732932)
at `fe4d683cef48664f733fa07a263590b9574c281a`, event `workflow_dispatch`, branch
`main`, attempt 1. The run, its single job and every reported step succeeded.
Source: `warehouse_builds.p5_9_manual_workflow_execution` in
[metrics.json](metrics.json). This completes only the approved P5.9 scope;
checklist reconciliation is the stopping point before new work.

Fresh prechecks independently verified exact remote SHA/workflow/green ordinary
CI, zero prior manual runs, reviewed account/direct grants and empty US target.
The command exited zero and returned the actual run URL. A durable attempt
receipt was saved before dispatch; no second dispatch, retry, repair publication,
permission expansion or credential inspection occurred.

Native compilation and all **21** service-account SELECT dry runs passed;
the largest actual estimate was **18,532,209 bytes**, below the **134,217,728-byte**
cap. Native dbt results contain **seven model successes and fourteen data-test
passes**, each with a distinct job ID and zero reported test failures. The
workflow's own-job accounting passed. The compiled/live staging SQL has both
public suffix bounds fixed to `20201101`, with sandbox materializations and
native unit fixtures excluded.

Independent owner-authenticated job list/get APIs retain exactly **21 terminal,
error-free query jobs**: three CREATE_VIEW, four CREATE_TABLE_AS_SELECT and
fourteen SELECT. All are submitted by the intended `ga4-github-dbt` account
in US/project `ga4-checkout-funnel`, under label `p5_9_37557732932_1`, with the
actual 128 MiB cap and 300-second native timeout. Every dbt node ID, including
zero-byte view/calendar jobs, matches the independent leaf inventory; the
per-job SQL hashes and processed/billed bytes match the workflow receipt.
There are no SCRIPT parents to exclude in this run.

Actual totals are **48,515,627 processed bytes** and
**178,257,920 billed bytes / 170 MiB**. Gross reference arithmetic at the gate's
saved $6.25/TiB rate is **$0.001013278961181640625**, before unverified allowance,
credits and invoice. Storage and Actions charges remain unverified.

Metadata APIs verify exactly three views and four unpartitioned/unclustered
plain tables in US `ga4_ci`, with null expirations and unchanged dataset access.
All seven actual schemas match the existing analyst relation schemas; live view
definitions match the reviewed compiled SQL. No audit/scratch relation exists
in `ga4_ci`. Table metadata reports:

| Table | Rows | Logical bytes |
|---|---:|---:|
| `fct_sessions` | 2,625 | 540,190 |
| `fct_funnel_daily` | 1,670 | 189,781 |
| `fct_product_daily` | 4,120 | 602,806 |
| `dim_date` | 1 | 40 |

These are isolated one-day validation resources, not new canonical business
metrics. They persist; no cleanup is authorized. Protected raw/analyst/replay
dataset access, inventories and complete saved relation metadata are unchanged.

Two API limits are retained explicitly:

- Jobs report the declared public `events_*` reference rather than a physical
  shard. The one-day scope is established by actual compiled/job SQL and live
  view definitions with constant November 1 suffix bounds.
  [Google documents constant suffix filtering](https://docs.cloud.google.com/bigquery/docs/querying-wildcard-tables).
- The owner identity's getQueryResults request for one service-account test
  received **403** on its anonymous result dataset. No private key, impersonation
  or new grant was used. Fourteen real passing/zero-failure outcomes are verified
  from the retained native dbt run results; independent job identity/state/errors/
  SQL/caps/bytes are verified through job metadata. Independent raw test-result
  values are **not claimed**. No extra SELECT was submitted to replace that read.

The single artifact `p5-9-37557732932-1` is retained locally with matching GitHub
SHA-256 digest and intact ZIP CRCs. Its only five files are plan, preflight,
accounting, compile manifest and build run results; no credential/log/workspace
upload was downloaded. The workflow's fourteen-day retention is recorded in
the artifact metadata. Receipts live under
`reports/.checks/p5_9_native_execution/`; source keys and hashes are saved in
metrics.json. Local audit corrections addressed the SDK submission serializer
omitting statistics, wildcard-reference metadata and unavailable result rows;
they changed only evidence checks, never the workflow or submitted jobs.

The original backfill cache remains **3,337 records / 355.384765625 GiB**, and
the original comparison summary remains **3,339 records / 355.4794921875 GiB**.
Adding only this independent 21-job scope yields **3,360 records /
381,871,456,256 billed bytes / 355.6455078125 GiB**, with
**167,884,357,632 bytes / 156.3544921875 GiB** to the unchanged **512 GiB**
boundary. Original backfill/comparison receipts and the **95-row CSV** are
preserved without resets, extension or replacement.

All earlier canonical metric values, completed Phase 5 evidence, exports,
configs/code and **300 owner Power BI files plus their Git index/status** pass
preservation checks. Only additive native evidence and current checklist/handoff
documentation are updated. No full suite, report/BI regeneration, extra native
query/dry run, Airflow/Docker activation, IAM/key/secret change, push, tag or
deletion occurred. The owner's later steering is honored: no further temporary
script approval requests or cloud reads are needed; reconcile the current
checklist and stop before another task.
