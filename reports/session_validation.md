# Approved session view build and validation

The owner approved Human step #7 / P2.3 only. The repository started clean on
`main` at `67013dd`. The current model retains first_visit events without a
session ID for user cohorts; session facts still require both key fields.

After current compilation and five successful dry-run preflights, this exact
command completed successfully:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- dbt build --project-dir dbt --profiles-dir dbt --select int_sessions --exclude test_type:unit
```

dbt reported `PASS=5 WARN=0 ERROR=0 SKIP=0`: one logical view and four read-only
data tests. It created `ga4-checkout-funnel.ga4_analytics.int_sessions` in US.
All four tests returned zero failures. No unit tests were selected.

Evidence: [metrics.json](metrics.json), `warehouse_builds.p2_3_int_sessions`.
Current estimates and SQL hashes are in [dry_runs.json](dry_runs.json),
`p2_3_revised_preflight`. Earlier evidence keys remain unchanged.

| SELECT preflight | Estimated processed bytes | Key under p2_3_revised_preflight.queries |
|---|---:|---|
| Full current session model | 1,248,818,019 | `int_sessions` |
| Session ID not null | 995,193,539 | `not_null_int_sessions_ga_session_id` |
| Start date not null | 1,038,149,379 | `not_null_int_sessions_session_start_date` |
| User ID not null | 995,193,539 | `not_null_int_sessions_user_pseudo_id` |
| Session-pair uniqueness | 995,193,539 | `unique_session_pair_int_sessions_ga_session_id__user_pseudo_id` |

Each estimate is below the existing 21,474,836,480-byte per-query cap. Test
preflights inline the compiled model because its view did not yet exist. Dry
runs remain labeled `executed: false`; later execution is recorded separately.

Billing was verified disabled before execution using the read-only gcloud
command under `preflight.billing_check`. ADC billing metadata returned HTTP 403;
gcloud required approved filesystem escalation to access its existing local
configuration. Neither action changed billing or displayed credential values.

The [official sandbox limits](https://docs.cloud.google.com/bigquery/docs/sandbox)
were checked: 1 TiB of processed query data per month. `preflight.quota` covers
all project jobs visible through `jobs.list` in the current UTC month, excluding
SCRIPT parents. It showed 26,704,999,297 processed bytes and 26,739,736,576 billed
bytes before the build. Both the estimates and the sum of all four test caps
fit within that allowance. This observation is not a billing statement or a
direct quota-service reading.

| Selected dbt job | Result | Actual processed bytes | Actual billed bytes |
|---|---|---:|---:|
| CREATE_VIEW int_sessions | Success | 0 | 0 |
| User ID not null | Pass; zero failures | 995,193,539 | 996,147,200 |
| Session ID not null | Pass; zero failures | 995,193,539 | 996,147,200 |
| Start date not null | Pass; zero failures | 1,038,149,379 | 1,039,138,816 |
| Session-pair uniqueness | Pass; zero failures | 995,193,539 | 996,147,200 |
| Total of selected jobs | Success | 4,023,729,996 | 4,027,580,416 |

Job IDs, types, timestamps, byte statistics, test caps, and SQL hashes are under
`warehouse_builds.p2_3_int_sessions.results`; the totals use
`.total_bytes_processed` and `.total_bytes_billed`. Billed-byte metadata is not
a dollar-charge claim; billing was disabled and no billing action was run.

Metadata reconciliation confirms the actual view definition matches the current
compiled SQL after ignoring comments and surrounding whitespace. All 27 actual
columns match declared names and order. The US logical view uses standard SQL,
is unpartitioned, and retains automatic sandbox expiration. Both staging views
and their schemas/definitions/timestamps are unchanged; project dataset inventory
and dataset expiration settings are unchanged. Evidence is under `.before`,
`.after`, and `.verification`; invocation and artifact hashes identify the build.

Eleven relevant Python regressions pass with no failures, errors, or skips,
including the actual portable cohort CTE with sessionless first_visit evidence.
The command and real JUnit totals are under `.verification.pytest`.

Reconciliation used only the approved four test results and read-only metadata
APIs. No additional aggregate/cohort query was executed. Historical business
numbers, BI exports, and prototype inputs retain their earlier SQL provenance;
the effect of the cohort correction on those aggregates was not measured here.
The four data tests verify keys and dates, not funnel/revenue totals or cohort
classification. No full catalog, marts, tables, raw loads, billing changes, or
backfills were executed. Work stopped before the separate P2.4–P2.6 scope;
remaining data tests and native unit fixtures also remain pending.
