# Autonomous local validation

The original checklist in [validation evidence](local_validation.md) remains the source of
truth. Local implementation and verification do not complete checklist items
whose required cloud, owner, GUI, Docker, or remote execution is pending.

`make verify-local` passed. Observations are saved in [metrics.json](metrics.json),
`prototype_validation.final_local`; actual command logs and JUnit output are in
ignored `reports/.checks/`.

This report preserves the earlier local checkpoint. Human Step #9 subsequently
completed its approved warehouse scope, and Human Step #8 now passes the actual
edited-DAG Astro import and post-continuation full-history Gitleaks checks; see
[runtime validation](runtime_validation.md) and `human_step8_validation` in
metrics.json. The pending statements below describe this historical checkpoint.
Actual scheduling/cloud replay, Power BI, remote CI and owner review remain pending.

| Check | Observed result | Evidence key under prototype_validation.final_local |
|---|---|---|
| Python tests | 85 passed; no failures, errors, or skips | pytest |
| Python and SQL lint | Passed, including real sandbox dbt macros with connections forbidden | lint |
| Report controls and JavaScript syntax | Passed; four Node tests use a DOM fixture | report_controls, javascript_syntax |
| Fresh dbt parse | Passed without warehouse access | dbt_parse |
| Manifest descriptions | 7 models, 118 declared columns, 14 data tests, 3 unit fixtures, 2 sources | dbt_manifest |
| dbt docs | Passed with an empty catalog and compilation disabled | dbt_docs |
| Existing BI CSVs | All five hashes, headers, and actual row counts match saved provenance | export_integrity |
| Offline report | Matches current saved inputs and generator exactly | interactive_report |
| Mandatory limitations and resume title | All four exact lines and the brief's title pass | wording |
| Git whitespace and ignored-artifact hygiene | Passed; credentials/raw data/Power BI files are untracked | git_whitespace, ignored_artifact_hygiene |

All pre-existing metrics sections match the starting `ba8920f` repository
exactly. New local evidence is added under `prototype_validation` and the bonus
report's `local_prototype`; no existing business result, job receipt, dry-run
estimate, BI provenance, or prior validation checkpoint was replaced.

The session cohort CTE correction passes actual portable SQL on a synthetic
fixture, but the revised full BigQuery SQL needs fresh preflights and execution.
The edited DAG passes syntax and declaration/context fixtures; actual Astro
import/scheduling and failed-job metadata permissions remain pending. Docker
socket access is denied in this sandbox, so the post-continuation Gitleaks scan
also remains pending. Earlier Astro and Gitleaks results describe older commits.

Cloud session/mart builds and dbt tests, source/raw loads and reconciliation,
replay/backfill idempotence and costs, the populated-raw partition comparison,
Power BI artifacts/filter validation, visual browser review, green remote CI,
and owner review remain blocked execution checks. Optional Kafka is deferred.
No new cloud query, resource, billing action, load, backfill, service account,
destruction, push, or release tag was performed during this continuation.
