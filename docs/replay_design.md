# Historical replay and incremental partition design

The analysis default is `pipeline_mode: sandbox`: filtered public shards feed
staging/session views and plain marts. `pipeline_mode: replay` instead reads the
raw DATE-partitioned table and incrementally replaces the three fact marts.
`dim_date` stays a complete-window plain calendar table; full refresh is disabled.

Staging and `int_sessions` retain the complete loaded historical window. The
normal refresh includes the run day and previous day, plus start-date partitions
of sessions touched on those days and users with first_visit evidence on them.
Every selected start-date partition contains its complete result, including
unaffected sessions sharing that date. Restricting input to two raw days, or
writing only touched sessions, would lose history during partition replacement.

Replacement dates are inferred from output rows by dbt's BigQuery
[insert_overwrite implementation](https://docs.getdbt.com/reference/resource-configs/bigquery-configs).
MERGE ON FALSE replaces selected complete partitions. Source reads preserve
historical context; this design does not claim every scan reads only two raw
partitions. A synthetic native fixture covers an older midnight crossing, a later
first_visit, and an unaffected session sharing a repaired date.

Native first-day rerun evidence verifies actual replacement arrays and complete
before/after fact/calendar fingerprints. All seven models/fourteen tests pass;
three fact creation timestamps remain unchanged. See [initialization](../reports/replay_initialization_validation.md)
and [native rerun](../reports/replay_rerun_validation.md). Full-window replay
subsequently completed all 92 dates with quality/reconciliation/accounting gates;
full-window row fingerprints and deliberately injected late events were not tested.

## Orchestration and accounting

The DAG runs extraction, source/raw reconciliation, then model compile/preflight/
build. Model SELECT estimates are saved per run and checked against the shared
positive byte cap; dbt applies the configured cap to executed jobs. SELECT dry
runs do not predict all DML/script bytes, so real job receipts remain necessary.

The `all_done` logger depends on every data task and uses run context if extraction
has no XCom. It counts completed failed-query bytes and script children once,
excluding SCRIPT parents. The final `all_success` leaf also depends on every data
task and logging, preserving a failed DagRun when its logger succeeds.

Automatic catchup is disabled, maximum active runs is one, and sample guards
reject out-of-window dates. The installed `CronTriggerTimetable` has a zero-length
interval at UTC midnight; `data_interval_start.date()` maps directly to the source
day. The 92 serialized/dry-listed dates and real runtime are documented in
[runtime validation](../reports/airflow_runtime_validation.md).

## Native failure and recovery

An explicit JSON boolean enables a controlled task failure only after real
reconciliation passes; the SDK no-retry exception leaves dbt upstream_failed,
logger successful, and the DagRun failed. SQL jobs succeeded, so this proves task
failure accounting rather than a deliberately failed SQL billing case.

Native non-partitioned reprocessing reuses the DagRun identity. An initial
label/date-only CSV key collided with prior history; restored receipts and UTC
execution-start/window keys preserve separate runs while same-window upsert
remains idempotent. [Recovery](../reports/airflow_recovery_validation.md) passes
all five tasks and adds an independent receipt while preserving previous rows.
The [completed backfill](../reports/airflow_gate23_validation.md) retains retries
on January 18/19/31 and the exact January 30 one-zero-byte-record supplement.

Replay uses separate US raw/analytics destinations and rejects the analytical
snapshot destination before extraction. Existing credentials remain read-only;
unknown estimates or actual byte totals fail closed. The immutable sample's
nonempty days are an assumption: removing an entire historical source day or
changing its window would need a different replacement/migration contract.
