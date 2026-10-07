# Offline validation checkpoint

On 2026-10-05, the safe continuation passed the checks below and stopped before
the separate P5.3 cloud build. Source: `continuation_validation.p6_4` in
[metrics.json](metrics.json). Earlier evidence is retained with all original
values; no completed cloud execution was repeated.

| Check | Actual result and scope |
|---|---|
| Python | 141 passed, zero failures/errors/skips; actual JUnit evidence |
| Snapshot | Every current Python/SQL/YAML implementation/test file matches the isolated tested snapshot; tracked Power BI generator definitions used so owner Desktop edits stay untouched |
| Python lint/format | Passed, 61 files |
| SQL lint | Standalone SQL, synthetic fixture SQL and all eight sandbox dbt SQL files pass with native macros and warehouse connections forbidden |
| JavaScript | Four Node control tests and syntax check pass; no new browser rendering claimed |
| Exports/report | All five local CSV hashes, headers and counts pass; HTML reproduces from saved real results without modifying it |
| Replay manifest | Seven models and 118 declared described columns; fourteen data tests and three unit definitions; parse/compile do not establish native execution |
| Documentation | Mandatory limitation/title wording, 74 relative file links and continuation-file whitespace checks pass |
| Secrets | Checksum-verified official Gitleaks 8.30.1 standalone release reports zero leaks across 94 reachable commits through `b17a345`; all branches scanned with redaction |
| Preservation | Every starting metric/dry-run value, Power BI file byte/index/status and offline HTML byte matches the starting checkpoint |

The first full snapshot passed 139 tests; the manual-preflight CLI cap follow-up
added two regressions, then the current full snapshot passed 141. This is local
repository validation, not a later remote CI run or validation of owner Desktop
edits. All runs use Python 3.12 and the existing pins/lockfile; the documented
`PYTHONMALLOC=malloc` workaround is retained without assigning a root cause.

Docker is unavailable in this WSL session. It was not repaired or reinstalled;
Needs from human #13 records starting Desktop/WSL integration before the current
edited-DAG native import. To complete the history scan independently, the pinned
[official release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)
was downloaded into a generated temporary directory, its archive checksum
verified against the release's checksums file, and the version checked before
the redacted read-only scan. Artifact/log hashes and exact command are saved
under `continuation_validation.p6_4.gitleaks`; logs/JUnit remain ignored under
reports/.checks/continuation. The final evidence/documentation commit follows
that scan; its exact coverage remains the saved `b17a345` checkpoint.

The continuation created no cloud resource, submitted no executed data SELECT,
performed no raw reload/rerun, changed no billing/IAM, and started no Airflow run,
backfill, workflow, push or tag. P5.3 native initial compile and seven
model/fourteen data-test SELECT dry runs are real read-only preparation, saved
separately under `warehouse_builds.p5_3_replay_preflight`. Unknown estimates and
actual byte totals are rejected instead of becoming published zero values.

The later native initialization, rerun, scheduling/accounting, complete 92-day
replay, partition comparison and manual workflow are documented in the linked
validation reports and canonical metrics. This historical local checkpoint retains
its original test counts, artifact provenance and narrower execution scope.
