# Gate #22: paused drain stopped at the retirement-log check

Historical status: **STOPPED; Gate #22 consumed.** The subsequent separately
approved [Gate #23](airflow_gate23_validation.md) completes January 31 and all
92 dates. The stopped checkpoint below remains unchanged. At that checkpoint,
January 31 remained unfinished. No
drain-ready receipt, DAG unpause, fresh dbt attempt 2 or completion is claimed.

Source: `warehouse_builds.p5_6_gate22_drain_stop` in [metrics.json](metrics.json).
The owner approved the [exact Gate #22 contract](airflow_gate22_validation.md).
Implementation/execution commit: `f9e66504ae5747054dd6ff128a161a255b42b83e`.
All 157 focused tests and changed Python lint/format checks passed before execution;
that result does not establish successful native recovery.

## Actual execution and diagnosis

The hash-bound script prepared a new Gate #22 plan/session, verified the frozen
native state and original accounting, and archived the 94-row CSV and January 31
preflight. Fresh monitor/watchdog guards were ready at the original
374,451,732,480-byte floor. The exact January 30 supplement passed against actual
saved receipts: native count 31 plus its one named zero-byte record reconstructs
the complete 32-ID API set. The CSV, lookup result and supplement were not edited.

At **2026-10-06 19:34:42.310463 UTC**, the controller unfroze only the existing
scheduler/worker container while keeping the DAG paused. Native metadata records:

- Heartbeat timeout at **19:34:42.516536 UTC**, with the original January 31 dbt
  UUID `01a10ea5-d0d8-7cee-b2a8-c776c2af8e6e` retained as failed attempt 1.
- Exact orphan reset at **19:34:42.568775 UTC**. The current dbt UUID becomes
  **`01a112b6-0a88-7b93-bee3-6f0c9ddc5fa4`**, state **null**, counter **1**,
  scheduler ownership null and configured `max_tries=3` unchanged.
- Old runner/dbt descendants exit, and the persistent LocalExecutor worker
  becomes idle. No worker daemon termination or stack restart occurs.
- The old task log contains a **CalledProcessError for the January 31 dbt build
  terminated by SIGTERM (15)**, followed by **403 Invalid auth token** while
  reporting terminal state. It contains no full PASS=21 or replay-build success.

The log check admitted the 403 retirement exception but omitted the SIGTERM
CalledProcessError produced by Airflow's own retirement. It therefore raised
**“Old task failed for another reason”** before writing drain-ready proof. This
is an overly restrictive local exception allowance; it is not evidence of a
BigQuery query error or a completed quality gate. No rule was widened after
activation. The coordinator froze/paused with both exits **0**; the monitor then
stopped on **“Drain coordinator exited”**, also with both exits **0**. Both guards
are now exited. The final `resume` command was never invoked.

## Exact stopped scope and partial warehouse writes

Existing **backfill ID 4**, all four backfill records, all **92 DagRuns** and
their run/start/label/window fields are unchanged. **91 sample dates** are
complete, including original November 1; **90 new dates** succeeded through
January 30. Only January 31 remains unfinished in the same running DagRun 92,
original start `2026-10-06 17:04:33.601315+00:00`, original label
`ga4_80f0c3dbf9ccdecab8f9930e`.

All **459 other task rows**, the completed/upstream protections and ten earlier
native history records are unchanged. January 31 extraction/reconciliation remain
successful on attempt 1; logger/finish remain null with counters 0. January 18/19
dbt attempt 2 successes and their failure histories remain disclosed.

The old client submitted two insert-overwrite SCRIPTs at **19:34:44 UTC**. They
and their six children completed successfully, including after local retirement.
Actual existing SELECT-result APIs show that both `fct_sessions` and
`fct_product_daily` selected exactly:

```text
2020-12-28, 2021-01-12, 2021-01-20, 2021-01-29, 2021-01-30, 2021-01-31
```

These are the normal affected session-start partitions within loaded history.
Each SCRIPT has one selector SELECT, one MERGE and one DROP_TABLE child; child
bytes reconcile exactly to its parent. Their normal dbt cleanup removed only
`fct_sessions__dbt_tmp170503989330` and
`fct_product_daily__dbt_tmp170503988307`. Older orphaned temporaries remain.
No manual deletion occurred. Replay metadata confirms those two fact changes;
this is partial work, without a last-date funnel/quality/receipt completion.
Raw has **92 partitions** and its metadata is unchanged; the saved eight-signal
January 31 source/raw proof still matches. Analyst warehouse metadata is unchanged.

## Cumulative accounting and preservation

The stop audit used only existing job/result/table metadata APIs, with query/load/
mutation methods disabled. It submitted **zero SQL or dry runs**. It preserves
all **3,295** original job records and adds **eight** terminal error-free records,
all belonging to the original January 31 label. Parent/child totals reconcile
without double counting. All **3,303** records are terminal without query errors.

| Measure | Audited value |
|---|---:|
| Cumulative billed bytes | **374,514,647,040** |
| Cumulative billed GiB | **348.7939453125** |
| Additional Gate #22 bytes / GiB | **62,914,560 / 0.05859375** |
| Additional gross query proxy, saved $6.25/TiB | **$0.00035762786865234375** |
| Original hard stop / per-query cap | **512 GiB / 4 GiB** |
| Remaining headroom bytes / GiB | **175,241,166,848 / 163.2060546875** |
| Original CSV rows retained byte-for-byte | **94** |

These costs cover the original backfill accounting window, not all account
charges or an invoice. Current CSV SHA-256 remains
`990d1cd0232b04dfe337ecc9b5a64c7c0354e9e5d231d4b626204fefb9f99508`.
All original baseline, stop receipts, metrics values, JUnit and retained artifacts
are preserved. The current cumulative cache expands by the eight actual records;
its original contents remain in Gate #21 evidence and the Gate #22 plan.

Owner Power BI file bytes/index/status, configuration, task sources, canonical
exports/report and analyst metadata are preserved. All three container identities,
zero restart counts and named PostgreSQL/log volumes are unchanged. The DAG is
paused, workers frozen, guards exited. No new backfill, task clear/state repair,
configuration/authentication bypass, full suite, IAM/workflow, cost experiment,
push or tag occurred. P5.6 remains incomplete.

## Minimum next recovery, separate Gate #23 proposal only

Gate #22 cannot be repeated: the starting task state and UUID have changed, and
its stop explicitly consumes approval. The minimum next scope is an **already
retired** recovery, anchored to the exact null/counter-1 UUID above, failed old
UUID/history, timeout/orphan records and saved attempt log hash. Preserve all
current completed/upstream rows, the same backfill and original run/label/window,
the **3,303-record / 348.7939453125 GiB** floor, all 94 receipts and the unchanged
exact January 30 supplement.

The saved terminal attempt log SHA-256 is
**`9f0eb62847e9356c4cd660614890cd9fceb6e908236c297685084e562029d0d0`**.
Its exact exception types, timestamps and exception-value hashes are recorded
under `january31_native_log_exceptions` in the stop evidence. No generic failed
dbt attempt may use this receipt.

Implement a separate Gate 23 plan/session and narrowly validate this specific
saved retirement evidence; do not grant a generic SIGTERM exception or repair
native state. With fresh guards and the DAG paused, prove the old process births
remain gone and every persistent executor is idle. Unfreeze the existing worker
only after those barriers, refresh native/accounting checks, and require readiness
no older than 60 seconds before one DAG unpause. Any missing evidence, changed
identity, failure, guard loss or 512 GiB equality/excess stops without continuation.

Allow **one fresh January 31 dbt attempt 2 only**, then the existing logger/finish
on their first attempt. No source/raw reload, completed-run reprocess or other
date. Keep native `max_tries=3` unchanged; guards reject another retry/reset.
The new dbt attempt repeats its normal seven-model/fourteen-test build with
current heavy-query preflights, US isolated destinations and the 4 GiB cap. Normal
affected historical replay partitions may be replaced; retain every actual
selector. Require PASS=21, all five task successes, strict exact January 31 logger
IDs/count/bytes including both attempts and lookup accounting, final 95-row CSV,
all job records terminal/error-free, preserved history/owner files/volumes and a
paused final DAG. No additional audit SQL or full suite.

Focused validation must cover the newly anchored null/counter-1 state and reject
changed UUID/history/event/log/provenance, unknown dbt errors and early/third
attempts; protect the 3,303-record floor, all 94 receipts and exact supplement;
and stop on process overlap, busy executor, stale readiness, guard loss or 512 GiB
equality. Retain Gate 20/21/22 regressions. Activation also requires fresh read-only
native/container/accounting barriers; synthetic tests alone cannot pass them.

The saved adjacent-date **one-dbt-attempt proxy** is **7,021,264,896 bytes /
6.5390625 GiB / $0.0399112701416015625 gross**. It is not a dry run, upper bound
or invoice; the logger and any in-flight billing remain cumulative. Proxy headroom
after that amount is **156.6669921875 GiB**; the actual stop stays at 512 GiB.

Proposed commands after the separate correction and focused three-file tests:
**Gate 23 is not implemented or activated; current CLI rejects that flag.**

```bash
export PYTHONPATH=src PYTHONMALLOC=malloc
export UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python

uv run --locked pytest tests/test_backfill_monitor.py \
  tests/test_backfill_supervisor.py tests/test_backfill_recovery.py \
  --junitxml=reports/.checks/p5_6_backfill_run/gate23_diagnosis/focused_tests.xml
uv run --locked ruff check src/pipeline/backfill_monitor.py \
  src/pipeline/backfill_recovery.py tests/test_backfill_monitor.py \
  tests/test_backfill_recovery.py
uv run --locked ruff format --check src/pipeline/backfill_monitor.py \
  src/pipeline/backfill_recovery.py tests/test_backfill_monitor.py \
  tests/test_backfill_recovery.py
git diff --check -- src/pipeline/backfill_monitor.py \
  src/pipeline/backfill_recovery.py tests/test_backfill_monitor.py \
  tests/test_backfill_recovery.py

uv run --locked python -m pipeline.backfill_recovery prepare \
  reports/.checks/p5_6_backfill_run/baseline.json --owner-gate 23 \
  --stopped-state reports/.checks/p5_6_backfill_run/gate22_session/stopped_airflow.json \
  --stopped-jobs reports/.checks/p5_6_backfill_run/gate22_session/stopped_jobs.json \
  --completed-evidence reports/.checks/p5_6_backfill_run/gate22_session/stop_evidence.json \
  --accounting-supplement reports/airflow_gate22_accounting_supplement.json \
  --backfill-id 4 --retry-run-id 'backfill__2021-01-31T00:00:00+00:00' \
  --retry-task-id dbt_build --maximum-attempt 2 --owner-go-recorded

uv run --locked python -m pipeline.backfill_supervisor start \
  reports/.checks/p5_6_backfill_run/baseline.json \
  --state-container ga4-checkout-funnel_5b4d14-api-server-1 \
  --recovery-plan reports/.checks/p5_6_backfill_run/gate23_recovery_plan.json \
  --session-dir reports/.checks/p5_6_backfill_run/gate23_session --owner-go-recorded

uv run --locked python -m pipeline.backfill_recovery drain \
  reports/.checks/p5_6_backfill_run/gate23_recovery_plan.json --owner-go-recorded
uv run --locked python -m pipeline.backfill_recovery resume \
  reports/.checks/p5_6_backfill_run/gate23_recovery_plan.json --owner-go-recorded

# Only after the monitor reports complete below the original hard stop:
uv run --locked python -m pipeline.backfill_recovery collect \
  reports/.checks/p5_6_backfill_run/gate23_recovery_plan.json
```

Stop for a **separate owner go** on this exact next scope.
[runbook](../docs/runbook.md) requires **“Show the exact command and scope, then wait
for ‘go’”** for backfills/possible charges. The approved Gate #22 contract also
requires a new reviewed go after any runtime stop. P5.7, IAM/workflow and release
remain separate.
