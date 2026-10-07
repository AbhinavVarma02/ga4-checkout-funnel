# P5.6 prior controlled failure and recovery preparation

Status: **local preparation PASS; native execution BLOCKED at owner gate #16**.
The separately approved [first-day integration](airflow_first_day_validation.md)
is complete. The [next gate](airflow_failure_validation.md) contains exact commands
for an intentional failed run followed by conditional same-day recovery.
Source: `continuation_validation.p5_6_failure_preparation` in
[metrics.json](metrics.json). No diagnostic or recovery run has executed.

The optional `ga4_validate_failure_after_reconcile` DagRun flag accepts only a
JSON boolean, defaults false and rejects malformed values before constructing
a cloud client. With true, the actual source/raw reconciliation must return
successfully before the native SDK `AirflowFailException` is raised. Missing
results and actual mismatches retain their original errors. The installed
exception's documented behavior and task-runner handler confirm no retry for
the deliberate failure. Ordinary configured retries are unchanged.

The existing all_done logger and all_success final leaf are retained. Native
execution must prove that dbt is skipped, the logger succeeds and the DagRun
remains failed. The conditional recovery creates a new same-day run with false
after those checks pass. Clearing the diagnostic run would retain its flag and
is outside the gate. A task failure after successful SQL does not establish
native failed-SQL byte accounting; failed_query_jobs may correctly remain zero.

Actual preparation checks:

- 197 local tests pass in an isolated current-source snapshot with tracked
  Power BI definitions. This verifies project behavior without replacing owner
  Desktop edits or claiming another Desktop run. The 74 related host tests also
  pass. New cases cover strict flag/configuration types, ordinary reconciliation,
  deliberate failure ordering, real mismatch precedence and missing results.
- Current native Astro import passes one test with four recorded warnings.
  No dependency, image or package pin changed. Import errors are empty.
- Thirteen installed SDK callback checks pass in a network-disabled disposable
  container with all external I/O mocked and cloud methods forbidden. These
  verify the actual exception class and default/explicit flag behavior; they
  create no task instance or run.
- The installed backfill CLI accepts the exact diagnostic configuration and
  `completed` reprocessing. Its dry run lists only 2020-11-01 and returns before
  creation. Afterward the DAG remains paused with one successful run, one
  completed backfill and five successful task instances, all from #15.
- The latest stored Airflow DAG source matches the mounted updated file. All
  health components pass. Existing container identities/start times/restart
  counts, image, owner configuration and persisted database/log volumes are
  preserved during this preparation.
- Python lint/format, canonical exports/mandatory wording, relative file links,
  changed-file whitespace and preservation checks pass. Counts and artifact hashes
  are recorded in metrics.json; original logs stay ignored under
  `reports/.checks/p5_6_failure_prep/`.

All previous metrics/dry-run values, the two native CSV rows/bytes, offline
report, owner configuration and all 300 owner Power BI files/index/status are
preserved. Preparation submitted no executed cloud query/load/mutation, new
raw date, failed run, recovery or non-dry backfill. The native outcome remains
pending. Full-window caps/allowance, the 92-day backfill, cost comparison and
IAM/manual workflow retain independent gates.

The pinned, checksum-verified Gitleaks 8.30.1 scan passes all 113 reachable
commits through `b46a541` with zero unresolved findings. Its initial scan
flagged the saved health response checksum as a generic API key; the checksum
was independently matched to the local artifact. [.gitleaksignore](../.gitleaksignore)
adds only that exact commit/file/rule/line fingerprint and retains the earlier
noncredential-path exception. No rule or path is broadly excluded. The final
metadata/exception evidence commit follows the scan.

## Subsequent native outcome

The separate #16 owner go executed [the real controlled task failure](airflow_failure_validation.md). Its reused run identity triggered CSV preservation/identity failure and the explicit stop-before-recovery condition. Original receipts are restored and the local identity fix is validated. [Repaired recovery #17](airflow_recovery_validation.md) remains pending. The preparation fields above describe their historical checkpoint.
