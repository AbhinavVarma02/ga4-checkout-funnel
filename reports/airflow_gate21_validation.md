# Gate #21: January 19 recovered; stopped on January 30 accounting count

Status: **STOPPED; no further resume authorized.** The owner replied `go` to the
reviewed [Gate #21](airflow_gate21_validation.md) at committed preparation
`ffbda58`. Existing backfill **4** was resumed once. January 19's native dbt
attempt **2** succeeded and the backfill advanced through January 30. The
monitor then found an exact CSV/job-inventory count mismatch and froze workers
before pausing the DAG. P5.6 remains incomplete; recovery review **#22** is
required. Do not repeat the consumed execution script or alter its receipts.

Source: `warehouse_builds.p5_6_gate21_accounting_stop` in
[metrics.json](metrics.json). Earlier Gate #20 evidence and all preparation
values remain unchanged.

## Execution and stop

The approved script/source hashes, owner files/configuration and original
267.84375 GiB floor passed preflight. A separate Gate #21 plan and session were
created; no prior evidence or accounting window was reset. Both detached peers
became ready at **16:50:42.227195 UTC** on October 6. The paused-DAG retirement
barrier passed at **16:50:46.595968**, and the guarded DAG unpause succeeded at
**16:50:50.867800**. No task clear, manual state repair, second backfill,
authentication/heartbeat/configuration change or stack restart occurred.

January 19's exact reset UUID was scheduled as dbt attempt **2** in its original
DagRun. Its other four tasks remain successful on attempt **1**. Native logs
record seven models/fourteen tests passing. The original failed attempt history,
UUID, log, DagRun start/label/window and Gate #20 receipts remain intact. January
20–30 then succeeded with all five tasks on first attempts; no further retry
was observed.

At **17:05:06.385 UTC**, the monitor detected
`Completed-run CSV differs from native job accounting`. Its stop receipt at
**17:05:08.129980** records scheduler-freeze exit **0** and DAG-pause exit **0**.
Observed billing at the stop was **368,517,840,896 bytes / 343.208984375 GiB**.
The 512 GiB boundary was not reached. Both detached guards subsequently exited.
No continuation followed the stop.

## Exact accounting discrepancy

January 30's native logger job
`13f73d8d-2172-4425-a8c8-7b2ab35ad91d` returned **31** leaf-job records. Its
unchanged CSV row also reports **31** jobs. The independently completed API
inventory contains **32** leaf jobs for label `ga4_44f47f071958c38219f810e7`.

| January 30 measure | Native CSV / saved lookup | Independent API inventory |
|---|---:|---:|
| Leaf query-job count | **31** | **32** |
| Processed bytes | **6,943,626,134** | **6,943,626,134** |
| Billed bytes | **7,066,353,664** | **7,066,353,664** |
| Query errors | **0** | **0** |

The one omitted record is **`c509e367-500b-4f64-be2c-d94c34066e69`**, a successful
zero-byte SELECT for the dbt `fct_funnel_daily.step_name` non-null test. It is
not a SCRIPT summary, script child, logger lookup or cache hit. Its current API
label matches the run. It was created at **17:04:24.263 UTC** and ended at
**17:04:25.304**. Both are inside the logger's original window
**17:03:26.319173–17:04:27.986298 UTC**, before the lookup's submission at
**17:04:29.049**. It processed/billed **0/0 bytes**.

This establishes the precise saved-result omission, not its internal BigQuery
cause. Metadata visibility delay is a possible explanation; it was not proved
by another INFORMATION_SCHEMA query, and no such query was submitted. No query
error or byte-total disagreement was observed. The guard correctly stopped
because exact job membership/count is required; matching money totals do not
waive that rule.

The original 31-job CSV row and lookup result remain unchanged. The full
32-job API evidence and omitted test record are saved separately in
`gate21_session/january30_count_mismatch.json`. Do not silently replace the
native receipt, fabricate a 32-row lookup result or rerun successful January 30
tasks to repair this evidence.

## Stopped remaining state

Fresh read-only native metadata verifies **90 successful new dates through
January 30**, plus the original successful November 1: **91 native completed
sample dates**. Of those new dates, **89 through January 29** have fully agreeing
task/quality/CSV/job evidence. January 30's five tasks and quality gate pass,
but its exact logger count is unresolved.

Only **January 31** remains unfinished:

- Same existing DagRun ID **92**,
  `backfill__2021-01-31T00:00:00+00:00`, state `running`.
- Original start **2026-10-06 17:04:33.601315+00:00**, label
  **`ga4_80f0c3dbf9ccdecab8f9930e`**.
- Extraction and reconciliation: success, attempt **1**, retained unchanged.
- dbt: frozen `running`, attempt **1**, UUID
  **`01a10ea5-d0d8-7cee-b2a8-c776c2af8e6e`**.
- Logger and finish: unset, counters **0**.
- One dbt process and one busy persistent executor worker are frozen; no native
  PASS=21 or full dbt quality success for January 31 is claimed. The old task's
  heartbeat/authentication may become stale during this stop; another in-place
  resume is not promised.

Existing backfill **4** and all backfill records are unchanged; no new record
was submitted. Completed/upstream task identities and histories remain
preserved. January 18 and January 19's historical dbt attempt **2** must both
remain disclosed.

## Audited cumulative accounting

Free job APIs found **11** additional records that were absent from the
monitor's stopped cache. Already submitted cloud work finished after clients
froze; those bytes remain in the original cumulative window. API inspection
verifies every submitted record terminal without query errors, all new job
statistics, complete SCRIPT child membership, and nonduplicated parent/child
accounting. No job was resubmitted by the audit.

| Measure | Audited value |
|---|---:|
| Total submitted job records | **3,295**, all terminal without query errors |
| Gate #21 added records | **442** |
| Cumulative billed bytes | **374,451,732,480** |
| Cumulative billed GiB | **348.7353515625** |
| Gate #21 added billed bytes | **86,856,695,808** |
| Gate #21 added billed GiB | **80.8916015625** |
| Additional billing after monitor stop | **5,933,891,584 bytes / 5.5263671875 GiB** |
| Original unchanged stop | **512 GiB** |
| Remaining headroom | **175,304,081,408 bytes / 163.2646484375 GiB** |
| Unchanged query cap | **4 GiB** |
| CSV receipts | **94**, all **82** pre-Gate #21 values retained |
| Loaded raw partitions | **92** |

All original **2,853** cached job records/statistics are preserved. The cumulative
window does not restart at this gate or at the monitor stop. At the saved
$6.25/TiB planning rate, arithmetic is **$0.4937231540679931640625** additional
Gate #21 gross query cost / **$2.1285116672515869140625** cumulative gross query
cost. These are not an invoice, account-wide spend, remaining allowance/credit
or storage/other charges. The window is the original Gate #18 backfill window.

## Validation and preservation

Existing result APIs independently verify all **13** January 19–31 source/raw
comparisons, with all **eight signals** equal. All **12** completed dates have
actual seven-model/fourteen-test success, actual replacement-array results and
logger byte totals agreeing with independent leaf totals. For **11** dates
through January 29, logger job IDs/counts agree exactly; January 30 retains the
single documented zero-byte omission. Native January 30 logs and artifacts
were captured after the stop without rerunning it.

The DAG is paused; the existing scheduler/workers are frozen; the API server is
available; both guards have exited; both containers have **zero restarts**.
Their identities and database/log volume names match Gate #20. Owner Power BI
files/index/status, owner configuration, pipeline task source, canonical exports,
offline report and analyst warehouse metadata are unchanged. Earlier metrics,
baseline, plan/phase/stop/log/JUnit evidence and current failed-count receipts
are retained. The 105 focused tests remain the preparation result; no tests or
full suite were rerun during execution. No full-row snapshot equality or native
injected late-event proof is added.

The audit submitted **zero SQL**, used existing job/results/table and local
native metadata only, and preserved all CSV bytes. No P5.7 experiment,
IAM/workflow, owner-data deletion, push, tag, release or further task activation
occurred. The unexecuted completion collector/audit remains unexecuted because
the native monitor stopped; no full-window completion evidence is claimed.

## Next owner boundary

**Needs from human #22 is BLOCKED on reviewed accounting repair and last-date
recovery, then owner go.** First define a fail-closed way to retain January 30's
native 31-row receipt while publishing its independently verified 32-job count
and unchanged byte totals. Reconcile exact IDs rather than accepting a generic
zero-byte exemption or issuing another paid lookup without approval. Preserve
all earlier values and do not clear/reprocess January 30.

Then review January 31's frozen attempt/physical state and heartbeat/auth
retirement before any fresh task attempt. Preserve its DagRun, upstream
successes, task history and original start-derived label/window. Keep backfill
4, the 4 GiB/query cap, US isolated targets and cumulative floor
**348.7353515625 GiB** toward the original **512 GiB** stop. Do not reset costs,
repeat Gate #21 or reuse its live phase/receipts.

Retain ignored `reports/.checks/p5_6_backfill_run/gate21_session/`, especially
`stop_evidence.json`, `stopped_airflow.json`, `stopped_jobs.json`,
`january30_count_mismatch.json`, `saved_result_validation.json`, native logs,
readiness/drain/resume/terminal receipts and the original baseline/cache. These
artifacts are present in this WSL workspace, not a fresh clone. The approved
[Gate #21 stop contract](airflow_gate21_validation.md) explicitly requires
a separately reviewed recovery after a stop. This checkpoint provides no next go.
