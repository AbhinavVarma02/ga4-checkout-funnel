# Gate #19 existing-backfill continuation: stopped on native retry

Status: **STOPPED; DAG paused and scheduler/workers frozen. P5.6 remains incomplete.**
The owner approved the presented Gate #19 scope with `go`. Both detached guards
established a fresh heartbeat, and the two approved unpause commands succeeded.
Only existing backfill **4** resumed; no second submission, clear, manual
reprocessing, stack rebuild/restart, owner configuration change, or full test
suite occurred.

Source: `warehouse_builds.p5_6_gate19_resume_stop` in [metrics.json](metrics.json).
The earlier [Gate #18 checkpoint](airflow_backfill_validation.md) remains historical
evidence; its original values are preserved.

## Actual outcome and stop cause

**2021-01-18 succeeded**, advancing to **78 successful new dates through January 18**,
plus the preserved original November 1 success: **79 completed dates of 92**.
The original 77 November 2–January 17 successes remain unchanged.

The January 18 `dbt_build` task was running at attempt 1 before unfreezing.
At `2026-10-06T02:54:03Z`, the scheduler detected its expired heartbeat and marked
it for retry. The task's native identity changed and its counter advanced to
**attempt 2**, which succeeded. Both dbt attempt logs contain **seven successful
models / fourteen passing tests**; attempt 1 then failed to report its terminal
task state to the supervisor. Successful SQL/dbt output does not establish a
successful first-attempt Airflow task.

The monitor did not observe the brief retry state in its sampled metadata. It
detected attempt 2 while validating the completed day's five first-attempt task
requirement. **January 19 had already begun**. This observation delay is a
limitation; the guard must not be described as having stopped before retry work.
At `2026-10-06T02:55:29.454235Z`, both automatic worker freeze and API-server DAG
pause succeeded. Docker and native metadata independently verify the frozen,
paused state. Both detached guards exited after the terminal stop.

**Thirteen dates remain unfinished:** January 19 has completed extraction and
eight-signal source/raw reconciliation, with `dbt_build` frozen on attempt 1;
January 20–31 are queued. Raw metadata has **80 populated partitions**. Terminal
query jobs do not establish completion of January 19's active task or DagRun.

## Audited accounting and preserved evidence

Free existing job/result APIs audit **2,843 submitted job records**, all terminal
without query errors. The original **2,801 cached job records** remain identical;
new records extend the same cumulative approval window.

| Actual accounting | Value |
|---|---:|
| Original stopped-window billed bytes | 276,061,749,248 |
| Additional Gate #19 billed bytes | 6,290,407,424 |
| Additional Gate #19 GiB | 5.8583984375 |
| Cumulative billed bytes | 282,352,156,672 |
| Cumulative billed GiB | 262.9609375 |
| Original cumulative hard stop, GiB | 512 |

The 512 GiB checkpoint was **not reached**. SCRIPT parent summaries are excluded
when children are counted; logger lookups are included. January 18's actual lookup
job IDs and bytes exactly match the independent leaf inventory, including both
attempts' SQL. Its eight source/raw signals agree; January 19's completed
reconciliation also agrees. The CSV now has **82 rows**, preserving all **81**
pre-resume row values and adding January 18's successful execution receipt.

At the **saved $6.25/TiB planning rate**, query-only gross arithmetic is
**$0.0357568264007568359375 additional** / **$1.6049861907958984375 cumulative**.
This is not an invoice; account-wide allowance, credits, storage and other charges
remain unknown. No extra paid verification SELECT was submitted.

All **300 owner Power BI files**, their bytes/index/status, owner configurations,
canonical exports, offline report, prior metric values, original baseline,
original stop receipts and saved JUnit files are preserved. Analyst warehouse
full metadata is unchanged. Raw/fact creation times, schemas, partitions,
clustering, US location and expiration settings retain their approved values.
Docker database/log volumes were neither rebuilt nor deleted.

The original stopped receipts and metrics snapshot are additionally preserved
under ignored `reports/.checks/p5_6_backfill_run/gate19_stopped_archive/`.
Current audit, native state, both January 18 dbt logs, partial January 19 logs,
scheduler heartbeat-timeout evidence, supervisor receipts and their hashes are
retained in that same existing WSL evidence directory. Preserve it for handoff.

The temporary preflight initially compared against upstream Airflow `3.3.2`;
it was corrected to the saved/installed `3.3.2+astro.1` before activation. The
ADC billing read returned 403; the documented read-only gcloud fallback verified
enabled billing. These harness/access incidents caused no query or worker
activation. Runtime pins and owner settings were unchanged.

## Remaining recovery boundary

**Needs from human #20 is BLOCKED on a separately reviewed recovery scope.**
Gate #19 approval is exhausted at its required unexpected-retry stop. Do not
repeat its unpause commands or activate another guard session now.

A future proposal must account for the active January 19 task's stale heartbeat,
preserve the completed January 18 attempt history, and define explicit retry
handling and earlier retry detection. No automatic retry acceptance, heartbeat
rewrite, task clear/reprocessing or configuration change is authorized here.
Any reviewed continuation must reuse backfill 4 and the original cumulative
512 GiB ledger, preserving all completed dates and 82 CSV row values. Exact
recovery commands have not been prepared or approved; do not infer permission
from the consumed Gate #19 go.

The earlier **246 full / 56 focused** checks remain saved historical validation;
no new suite was run. Native execution/log/result/accounting and local preservation
checks above are actual Gate #19 evidence. Full-window completion, full-row
fingerprints, late-event injection, P5.7 cost comparison, IAM/workflow, push and
tag remain unperformed or separately gated.
