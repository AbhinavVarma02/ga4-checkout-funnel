# Approved sandbox mart build and reconciliation

Human Step #9 authorizes P2.4–P2.6 only. The repository started clean on `main`
at `513d03d`; P2.3 was already complete. The documented non-unit compilation
and all seven model SELECT dry runs passed before any mart creation. Ten current
mart data-test SELECTs also passed dry runs with their unbuilt dependencies
inlined. Exact estimates, SQL hashes, inventory, billing and allowance checks
are under `warehouse_builds.p2_4_marts.preflight` in [metrics.json](metrics.json)
and `p2_4_current_preflight` in [dry_runs.json](dry_runs.json).

Billing was verified disabled with the read-only gcloud command. It required
filesystem escalation for gcloud's existing configuration; no billing setting
changed. Observed monthly processed bytes were 30,728,729,293 before execution.
The conservative 24-query cap budget was 515,396,075,520 bytes, below the remaining
[1 TiB monthly sandbox allowance](https://docs.cloud.google.com/bigquery/docs/sandbox).
Visible job metadata is an observation, not a direct quota-service reading or
billing statement. Two later read-only validation retries are accounted for
separately; all executed reads stayed within the same per-query cap.

The exact approved command succeeded with `PASS=14 WARN=0 ERROR=0 SKIP=0`:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- dbt build --project-dir dbt --profiles-dir dbt --select fct_sessions fct_funnel_daily fct_product_daily dim_date --exclude test_type:unit
```

| Actual relation in ga4-checkout-funnel.ga4_analytics | Rows | Declared/actual columns |
|---|---:|---:|
| fct_sessions | 360,129 | 28 |
| fct_funnel_daily | 170,520 | 12 |
| fct_product_daily | 604,094 | 12 |
| dim_date | 92 | 5 |

All four are plain unpartitioned US tables, retaining sandbox expiration.
Actual CREATE TABLE SELECTs match the current compiled SQL. Actual schemas match
declared names and order. Only these four relations were added; all three
existing views, project dataset inventory and expiration settings are unchanged.
The four creation jobs and ten passing data-test jobs processed 2,723,624,796
bytes and report 2,786,066,432 billed bytes. Billed-byte metadata is not a dollar
charge claim. Evidence: `.models`, `.results`, `.after`, `.metadata_verification`
and byte totals under `warehouse_builds.p2_4_marts`.

Read-only checks against the actual tables pass:

- All 317 device/country session segments match saved independently reconciled
  event, session, purchase, revenue and any-order/strict reach values.
- All 3,170 segment/mode/step funnel aggregates match saved reach; daily grains,
  next-step reach, purchase leads and cumulative bounds have zero violations.
- All 4,761 product/category aggregates match saved reach, names, revenue and
  missingness; daily product grains and reach arithmetic have zero violations.
- An independent public-source grouping matches every actual session's first
  export date, event count, purchase count, USD revenue and first_visit cohort.
  Missing/extra sessions and all mismatches are zero.
- Calendar coverage and attributes match all 92 sample dates, without duplicates.

The current cohort contains 332,837 new-in-window sessions and 3,790 purchase
sessions in that cohort; both deltas from historical saved results are zero.
The sessionless-first_visit correction therefore changes neither count in this
sample. Historical analysis, BI export provenance and prototype inputs are
preserved. Evidence: `.reconciliation` and `.verification` under the same key.

The first reconciliation process exited with native status 139 after saving
all five query results but before publishing the final verification. Its cause
is unconfirmed. A successful recovery reused the exact completed session,
funnel and product jobs, strengthened null-sensitive cohort/calendar comparisons,
and executed only those two revised SELECTs after new dry runs. Earlier versions
remain under `.prior_reconciliation_attempts`; both attempts' actual bytes are
retained. A final resumption checks unchanged warehouse metadata and exact
completed query hashes before reusing saved results, then verifies them again.

Reproduce these read-only checks against the recorded build:

```bash
PYTHONMALLOC=malloc PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- python -m pipeline.mart_validation
```

Native unit fixtures and the full catalog are recorded in later P2.5/P2.6
checkpoints. No billing action, raw/replay resource, extraction, incremental DML,
Phase 5 load/backfill, owner-file deletion, remote push or release is authorized
by this scope.
