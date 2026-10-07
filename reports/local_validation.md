# Local and execution validation evidence

The recorded local checks, native warehouse/runtime execution, report artifacts
and historical replay are summarized below. The retained full-history Gitleaks
8.30.1 checkpoint scanned 145 commits through 5ecd917 with exit 0/no leaks;
individual checksum/source-reference false positives use exact historical
fingerprints, with no broad exclusions. Later documentation changes are outside
that saved scan's scope.

The prior `continuation_validation.final_closeout` checkpoint retains the
454-test JUnit/check logs and reused native evidence. Those checks remain valid;
no implementation, models, tests, workflows or runtime sources changed.

| Validation scope | Final evidence and result | Metrics source key |
|---|---|---|
| Required local tests/lint/checks | Passed: 454 Python tests, zero failures/errors/skips; Python/SQL lint, Node controls/syntax, dbt parse/docs, export provenance and HTML reproducibility | `continuation_validation.final_closeout.local` |
| Native dbt models/data/unit tests/catalog | Existing execution retained: seven models, fourteen distinct data tests, three native fixtures and 118 described actual columns; fresh offline manifest agrees | `warehouse_builds.p2_4_marts`, `.p2_5_tests`, `.p2_6_catalog.verification` |
| Real Astro/runtime | Existing real import/SDK/first-day native scheduling evidence reused; no Docker stack restart or Airflow activation | `human_step8_validation.astro_parse`, `continuation_validation.p5_6_airflow_runtime`, `warehouse_builds.p5_6_first_airflow_run` |
| Full-history secret scan | **Passed: exit 0/no leaks, 145 commits through 5ecd917**, after individually verified exact historical exceptions. Earlier remote green scan remains valid for fe4d683 only | `continuation_validation.p6_2_p6_4_closeout.gitleaks` |
| Power BI PBIX/screenshots/owner verification | Repository-backed PBIX checksum unchanged; four screenshots unchanged, prior PNG/visual evidence valid; owner confirms DAX/model/filter/interaction checks. P4.2 complete | `powerbi_desktop_artifact`, `powerbi_project_validation`, `bi_exports` |
| 92-day backfill | Original backfill 4 completes 92 dates / 460 successful task rows; 43 retained immutable Gate #23 artifacts reverified. January 18/19/31 retries and January 30 supplement disclosed | `warehouse_builds.p5_6_gate23_completion` |
| Idempotence and failure/recovery | Native first-day full-row mart equality; actual task failure/all_done logging and repaired recovery retained | `warehouse_builds.p5_3_replay_rerun.verification`, `.p5_6_controlled_failure`, `.p5_6_airflow_recovery` |
| Billed-byte/cost evidence | Existing 95-row CSV, complete native job accounting and filtered/unfiltered measured processed/billed bytes retained; account invoice/allowance/credits/storage not inferred | `warehouse_builds.p5_5_native_accounting`, `.p5_6_gate23_completion`, `partition_comparison`, `.p5_9_manual_workflow_execution.combined_recorded_scopes_accounting` |
| Green ordinary GitHub CI | Retained run 37555548304 at fe4d683 completed/success and all reported steps pass | `warehouse_builds.p5_9_manual_workflow_execution.preflight` |
| Successful manual BigQuery workflow | Retained run 37557732932, attempt 1; seven models/fourteen native zero-failure tests and independent job IDs/bytes verified. Owner anonymous-result API 403 is disclosed | `warehouse_builds.p5_9_manual_workflow_execution` |
| Documentation and scope wording | README/architecture/run instructions, runbook, metric definitions and dataset limitations reconciled; the four dataset limitations were checked; Desktop version/build 2.158.1177.0 64-bit is recorded in docs/versions.md | `continuation_validation.final_closeout.local.wording`; current owner version record in [versions.md](../docs/versions.md) |
| Preserve canonical metrics/owner files | Canonical numerical and all prior execution evidence preserved; only owner-removed walkthrough status and additive closeout evidence change. All 300 owner Power BI files/index/status, exports, screenshots, byte CSV and tags unchanged | `continuation_validation.final_closeout.preservation` |

The numerical query/accounting evidence and dashboard artifacts are retained.
Historical source scopes remain explicit; these recorded passes are not claims
of new cloud, GUI, workflow or production execution.

## Historical local validation checkpoint before staging approval

The safe local preparation is complete. This checkpoint does not establish a
warehouse deployment or full project completion. Machine-readable evidence is
saved in [metrics.json](metrics.json), `local_validation`; its `validated_commit`
identifies the implementation checked before this documentation commit.

| Check | Observed result | Source key under `local_validation` |
|---|---|---|
| Final pytest run | 66 passed; no failures, errors, or skips | `pytest` (actual local JUnit output) |
| Python lint and formatting | Passed | `python_lint`, `python_format` |
| dbt documentation | Passed with an empty catalog; no warehouse introspection | `dbt_docs` |
| Sandbox manifest | 7 models, 118 described columns, 14 data tests, 2 unit fixtures, 2 sources | `dbt_manifest` |
| Completed BI exports | Every checksum, column list, and row count matches provenance | `export_integrity` |
| Required limitations | All 4 exact lines appear once in README, memo, and resume ledger | `mandatory_limits` |
| Resume title | Exact brief title retained | `resume_title` |
| Git-history secret scan | 59 commits scanned, no leaks; redacted and network-disabled | `gitleaks` |

Full SQL lint and Astro DAG integrity parsing passed at the earlier P5.3
checkpoint; no model SQL or DAG edits followed those checks. They were not
rerun merely to refresh this document. See `earlier_checks` and the checkpoint
history in [validation evidence](local_validation.md). The JUnit file and dbt manifest/catalog
are generated local artifacts; their observations are retained in the metrics
file. The secret scan will run again after this checkpoint commit.

The existing analytical metrics were preserved exactly. Export integrity checks
read the existing CSVs locally and submitted no query. No cloud resource,
credential, billing change, warehouse build, load, or backfill was performed.

Warehouse builds and dbt tests, source/raw reconciliation, replay/backfill
idempotence, actual pipeline costs and the partition comparison, Power BI
DAX/filter validation and artifacts, green GitHub CI, and owner review remain
pending. The exact first cloud-resource command and scope are in Needs from human
#5; approval of that scope does not authorize later tables, billing, or loads.

Subsequent status: the owner approved that staging scope, and its build and
read-only reconciliation passed. See [staging validation](staging_validation.md)
for the later evidence and current [validation evidence](local_validation.md) for remaining gates.
