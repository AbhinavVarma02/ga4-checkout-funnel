# Runbook

This repository separates credential-free local checks, BigQuery analysis, and a
local Docker/Astro historical replay. Raw data and credentials are not committed.
The saved Power BI report uses CSV Import; the warehouse replay was validated
separately. [Metric definitions](metric_definitions.md), [replay design](replay_design.md),
and [versions](versions.md) describe the project contract and tested environment.

## Local checks and saved reports

Use Ubuntu, Python 3.12, and the committed uv lockfile:

```bash
make setup
make test
make lint
make prototype
make test-report
```

The prototype rebuild reads saved metrics and refuses to overwrite changed output.
It does not query BigQuery. `make verify-local` additionally records local JUnit,
lint, dbt parse/empty-catalog docs, export provenance, report reproducibility, and
scope wording under `prototype_validation.final_local`; it writes metrics/logs
locally. Missing ignored CSVs are reported as pending, rather than invented.

Completed native execution evidence is retained in [local validation](../reports/local_validation.md),
[dbt tests](../reports/dbt_tests_validation.md), [catalog](../reports/catalog_validation.md),
[backfill](../reports/airflow_gate23_validation.md), and
[manual workflow](../reports/manual_workflow_native_validation.md). Reproducing a
local check does not imply a new warehouse, GUI, or GitHub workflow execution.

## BigQuery configuration and dry runs

Copy `.env.example` to `.env` only if `.env` is absent. Configure your project,
US datasets, and a positive `BQ_MAX_BYTES_BILLED`. Keep credentials in the local
environment; use application-default authentication. All cloud commands below
can require your own project configuration and can incur charges when executed.

Sandbox mode is the dbt default: source wildcard suffix filtering, views, and
plain mart tables. Replay requires a billing-enabled project, raw DATE partitions,
an isolated analytics dataset, and cleared table/partition expiration settings.
Do not run incremental DML against sandbox/plain-table analytical snapshots.

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked dotenv run -- python -m pipeline.dbt_dry_run --all

PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked python -m pipeline.extract_day 2020-11-01 \
  --dry-run --run-label=example_20201101 --max-bytes-billed=33554432
```

The extractor creates/overwrites a raw day partition when `--dry-run` is omitted.
Model SELECT estimates are not complete insert_overwrite/DML costs; actual job
metadata and labeled per-run accounting are the cost evidence. Unknown estimates,
nonpositive caps, scope errors, and unknown actual bytes fail closed.

For a sandbox warehouse build, the existing `make dbt-build` target loads `.env`
and invokes native dbt. Inspect configuration, destinations, compiled SQL, and
dry-run estimates before executing it. The [source/model validation reports](../reports/mart_validation.md)
record completed builds; no fresh build is needed to view the portfolio artifacts.

## Historical replay and recovery

[Airflow instructions](../airflow/README.md) cover the pinned Docker/Astro project,
read-only credentials, ignored replay environment, paused DAG, and sample dates.
The validated backfill completed all 92 dates. Automatic catchup is disabled;
starting the stack does not initiate a historical load.

Extraction replaces a day's raw partition; reconciliation runs before dbt builds.
The dbt facts replace complete affected session-start partitions. The `all_done`
logger uses the execution window even if extraction has no XCom, counts script
children once, and excludes SCRIPT summaries. `finish` depends on all data tasks
and logging, so successful failure logging does not mask a failed DagRun.

The controlled failure happened after successful SQL reconciliation; it is a task
failure, not a deliberately failed SQL billing test. Recovery exposed that native
non-partitioned reprocessing reuses a DagRun identity. UTC-start labels and CSV
window keys preserve separate attempts. See [failure](../reports/airflow_failure_validation.md),
[recovery](../reports/airflow_recovery_validation.md), and
[complete backfill](../reports/airflow_gate23_validation.md). January 18/19/31 retries,
the January 30 one-record supplement, and retained task history remain disclosed.

## Power BI and CSV exports

Open [Breadcrumb.pbix](../powerbi/Breadcrumb.pbix) for the saved imported model.
For a fresh PBIP project, obtain the complete analytical CSVs first. The exporter
uses capped BigQuery SELECTs and can incur charges:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked python -m pipeline.export_bi
```

It exports the analytical models plus the independent category rollup, verifies
provenance, supports matching-job resume, and protects changed/incomplete files.
[Power BI setup](powerbi_build_guide.md) explains `ExportsFolder`, refresh, DAX,
filters, and [the disclosed monetary precision difference](../reports/powerbi_validation.md#monetary-presentation).
Desktop version/build is 2.158.1177.0 64-bit, recorded from the report review.

## Troubleshooting

| Symptom | Check |
|---|---|
| Missing ADC/project | Configure local application-default authentication and GCP_PROJECT_ID |
| Cap exceeded or unknown estimate | Inspect query scope and choose a known positive per-query limit; do not assume missing cost is zero |
| Docker unavailable | Start Docker Desktop and WSL integration before Astro commands |
| DAG import fails | Check the pinned Python variant and OpenTelemetry package pins |
| Source/raw mismatch | Inspect the failing date before replacing only that partition |
| Byte lookup cannot access job metadata | Verify ga4_run label, UTC window, and the identity's intended job-metadata permissions |
| PBIP CSV path/privacy error | Set ExportsFolder to your complete local exports and select an appropriate local-file privacy level |

The [partition comparison](../reports/partition_comparison_validation.md) measures
processed/billed query bytes, not account spend. Free allowance, credits, storage,
Actions charges, and invoices are unverified. The manual BigQuery workflow is an
isolated one-day proof with reviewed-SHA, credentials, empty-target, US, and cap
guards; adapting its fixed project/scope requires matching your own environment.
