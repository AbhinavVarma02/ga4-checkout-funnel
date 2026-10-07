# Gate #20: paused-DAG drain stopped at its deadline

Status: **STOPPED; no DAG unpause or planned dbt attempt 2.** P5.6 remains
incomplete. A separately reviewed recovery gate is required before activation.

Source: `warehouse_builds.p5_6_gate20_drain_stop` in [metrics.json](metrics.json).
The owner approved the [reviewed Gate #20 sequence](airflow_gate20_validation.md)
at execution commit `71249e577d4df624c989cf6dfa2b2c28ac230bcd`.

## What executed

The preparation verified frozen state, preserved owner files/configuration,
installed pins/queue filtering, enabled billing and the original accounting
window. It created a separate Gate #20 plan/session without resetting or deleting
earlier evidence. The detached monitor and watchdog became ready with a fresh
heartbeat at 282,352,156,672 billed bytes / 262.9609375 GiB.

At 15:17:01 UTC on October 6, only the existing scheduler/worker container was
unfrozen. The DAG remained paused throughout. Native metadata records a January
19 heartbeat-timeout event and failed attempt 1 in TaskInstanceHistory, with the
original task UUID preserved in that history. The current task UUID rotated,
its counter stayed at 1, and its state became `null`. Its DagRun identity, start,
label and window remained unchanged.

The original dbt process continued some SQL, then received SIGTERM. Its log
records CalledProcessError and **403 Invalid auth token** while reporting terminal
state. It contains no native PASS=21 or successful replay-build marker; January
19's dbt build and quality gate are not complete.

The approved `retirement_supported` barrier accepts first-attempt success or a
freshly evidenced `up_for_retry` state. The observed `null` state never satisfied
that barrier. At 15:20:03 UTC the 180-second deadline stopped both the coordinator
and monitor. Each receipt records freeze exit 0 and DAG-pause exit 0. The final
`resume` command was never invoked, and no drain-ready or resume receipt exists.
No fresh attempt 2 was launched.

After the stop, Docker/process metadata confirms the old runner/dbt descendants
are gone and the persistent LocalExecutor worker is idle. The scheduler remains
running but frozen; the API server remains running and available. Both have zero
restarts. Both detached guards have exited. This is a recovery task-state
contract failure, rather than a stale monitor heartbeat or the 512 GiB boundary.
The entire native internal callback path producing `null` has not been traced;
its state, UUID rotation, timeout event and original attempt history are directly
observed.

## Exact stopped scope

Existing full-window **backfill ID 4** and all backfill records are unchanged.
There are still **78 successful new dates through January 18**, plus the original
successful November 1: **79 completed sample dates**.

- **January 19:** same running DagRun; extraction/reconciliation remain successful
  on attempt 1. dbt is now unset (`null`) with counter 1 and retained failed
  attempt history. Its old processes are gone. Logging/finish remain unset with
  counter 0.
- **January 20–31:** the twelve original queued DagRuns and their task rows are
  unchanged.

There are **13 unfinished dates**. Every completed run/task, January 19's upstream
tasks, original start-derived label and all queued task identities are preserved.
January 18's historical dbt attempt 2 remains disclosed and unchanged.

## Cumulative accounting and preservation

Fresh free job APIs and the preserved ledger verify **2,853 submitted job
records**, all terminal without query errors. The original **2,843 records** are
unchanged; **10 new leaf records** belong only to January 19's original label.
There were no planned-retry jobs or jobs for later dates.

| Measure | Actual value |
|---|---:|
| Cumulative billed bytes | 287,595,036,672 |
| Cumulative billed GiB | 267.84375 |
| Additional Gate #20 billed bytes | 5,242,880,000 |
| Additional Gate #20 billed GiB | 4.8828125 |
| Unchanged cumulative stop | 512 GiB |
| CSV rows, all prior values preserved | 82 |
| Raw partitions, unchanged | 80 |

SCRIPT summaries/children are accounted without duplication. The unchanged
checkpoint was not reached. At the saved $6.25/TiB planning rate, additional
query-only arithmetic is **$0.0298023223876953125**; actual invoice, allowances,
credits, storage and other charges are not inferred.

All 300 owner Power BI files and their index/status, owner configuration,
canonical exports/offline report and analyst warehouse metadata are preserved.
Docker database/log volumes and earlier baseline, job records, native daily
logs, stop receipts and JUnit files are retained. The original cumulative window
must continue from **267.84375 GiB**, never from zero or the pre-Gate #20 floor.

The audit used native metadata and existing job/table APIs only: **zero audit
SQL submissions**, no extra paid verification SELECT. An audit JSON-path error
was corrected locally because the prior warehouse snapshot is nested under
`datasets`; preserved logs were reused. No recovery activation accompanied that
correction. The saved 79 focused tests and lint/format remain historical
implementation validation; no tests or full suite were rerun during execution.

## Saved evidence and next boundary

Keep the ignored original `reports/.checks/p5_6_backfill_run/` directory and its
new `gate20_session/`, especially `stop_evidence.json`, `stopped_airflow.json`,
`stopped_jobs.json`, `stopped_processes.json`, `stopped_warehouse.json`, the native
attempt 1 log, both stop receipts, ready/heartbeat/launch records and source
inspection. Metrics contains their artifact hashes and observed source values.

Do not repeat the consumed Gate #20 execution script, alter its phase/receipts,
clear tasks, hide failed history, weaken timeouts/authentication, restart the
stack, submit another backfill or resume scheduling. The next reviewed gate must
resolve the observed native unset task state while retaining physical retirement,
native history/UUID/attempt checks and the original cumulative 512 GiB guard.
No next recovery, P5.7, IAM/workflow, push or release is authorized by this stop.
