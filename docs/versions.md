# Tested project versions

Recorded environment for the completed GA4 analysis and historical replay.
Python/package pins remain in pyproject.toml, .python-version, and uv.lock.
Power BI Desktop version/build **2.158.1177.0 64-bit** was supplied during the
recorded Desktop review; a report build date is not inferred.

| Tool | Recorded version |
|---|---|
| git | 2.53.0 |
| uv | 0.12.23 |
| Python | 3.12.15 |
| Google Cloud SDK / bq | 587.0.0 / 2.1.39 |
| Astro CLI | 1.46.0 |
| GitHub CLI | 2.102.0 |
| Node.js | 24.21.0 |
| Docker client / engine | 29.8.1 / 29.8.1 |
| Docker Desktop | 4.93.0 |
| Power BI Desktop | 2.158.1177.0 64-bit |

## Pinned Python packages

| Package | Version | Purpose |
|---|---|---|
| dbt-core | 1.12.5 | Transformation framework |
| dbt-bigquery | 1.12.1 | BigQuery adapter |
| google-cloud-bigquery | 3.46.1 | Profiling and pipeline client |
| python-dotenv | 1.2.4 | Local environment loading |
| pytest | 9.1.1 | Tests |
| ruff | 0.16.10 | Python lint and format |
| sqlfluff | 4.4.0 | SQL lint |
| sqlfluff-templater-dbt | 4.4.0 | dbt SQL templating |

These are stable releases published on [PyPI](https://pypi.org/) as checked on 2026-10-04. Transitive versions are pinned in `uv.lock`.

## Pinned GitHub Actions

| Action | Version |
|---|---|
| actions/checkout | v7.0.1 |
| astral-sh/setup-uv | v10.2.0 |
| google-github-actions/auth | v3.0.0 |
| Gitleaks container | v8.30.1 |

The CI workflow installs uv 0.12.23, matching the locally verified version.

## Pinned Airflow container

| Component | Verified version |
|---|---|
| Astro Runtime image | `3.3-8-python-3.12` |
| Apache Airflow | `3.3.2+astro.1` |
| Python in Astro image | 3.12.14 |
| dbt Core / BigQuery in Astro image | 1.12.5 / 1.12.1 |
| OpenTelemetry API / SDK in Astro image | 1.45.0 / 1.45.0 |


The Astro image uses Python 3.12.14; the project environment uses Python 3.12.15.
The Python 3.12 Runtime variant and OpenTelemetry pins support the recorded native
DAG integrity check. Package versions are unchanged across the native model builds,
first-day rerun, failure/recovery, full replay, and manual workflow evidence.
