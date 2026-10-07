# Native replay and local validation checkpoint

This checkpoint records native first-day rerun equality and local repository
validation. Subsequent execution is documented in the related validation reports.

P5.3 now passes native first-day insert_overwrite, all seven models/fourteen data
tests and exact before/after row/date/revenue equality. Actual script child jobs
are included without double counting parents. [Native validation](replay_rerun_validation.md)
records the approved execution and local before-validator recovery.

P5.4 current strict reconciliation passes against the existing completed native
first-day query, whose SQL/parameter/result match the current implementation.
No duplicate SELECT was submitted. [Quality validation](reconciliation_validation.md)
records eight matching signals and nineteen focused field/null/cost tests.

The current Python source passes **183 tests**, zero failures/errors/skips, in an
isolated snapshot using tracked Power BI definitions. Full Python lint and
formatting (65 files) pass. Five CSV provenance checks, required wording and all
208 previously checked relative links pass. All starting metrics/dry-run values,
all 300 owner Power BI files' bytes/index/status and the offline report bytes are
preserved. New native/preparation evidence is added without changing canonical
full-window analyst numbers. Machine evidence:
`continuation_validation.p5_3_native_closeout` in [metrics.json](metrics.json).

Checksum-verified standalone Gitleaks 8.30.1 scans all **104 reachable commits
through 96f6867**, with zero unresolved findings. The initial scan reported one
noncredential source path added in 98a2b52: `package_provenance_source_key`
points to the existing `continuation_validation.p6_4` validation object.
Its meaning and target were verified. [.gitleaksignore](../.gitleaksignore)
excludes only that exact historical commit/file/rule/line fingerprint, with no
broad path/value exclusion or disabled rule. No credential values were displayed
and no history was rewritten. The final evidence commit follows this scan;
remote CI was not rerun and current Docker runtime remains unavailable.

Later native accounting, runtime, controlled task failure/recovery and the
complete 92-day backfill are recorded in [accounting validation](bytes_log_validation.md),
[runtime validation](airflow_runtime_validation.md) and
[backfill completion](airflow_gate23_validation.md). This report retains the
historical native rerun and local-check scope; it is not an execution instruction.
