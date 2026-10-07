# Approved native dbt data and unit tests

Human Step #9 / P2.4–P2.6 is the only approved execution scope. All 14 declared
native data tests have passed with zero failures: four unchanged int_sessions
tests from P2.3 and ten mart tests from the current P2.4 build. This combines
two actual invocations; no single all-tests invocation is claimed.

Evidence: `warehouse_builds.p2_5_tests.data_tests` in
[metrics.json](metrics.json), with exact test IDs and links to the earlier result
keys. All persistent relations and dataset settings remain unchanged after
the unit execution.

The real, unmodified native command succeeded with `PASS=3 WARN=0 ERROR=0 SKIP=0`:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- dbt test --project-dir dbt --profiles-dir dbt --select test_type:unit
```

All three synthetic fixtures passed:

- Midnight assignment, repeated cart after an item view, purchase revenue and
  in-window first-visit classification.
- Timestamp ties, shared numeric session IDs across users, null-user exclusion,
  and a later sessionless first_visit classifying an earlier valid session.
- Complete affected start-date selection with synthetic replay overrides,
  including older midnight crossings and later first_visit users.

The final fixture uses synthetic inputs and macro overrides. It does not execute
cloud replay, incremental DML, raw extraction, real partition replacement or a
Phase 5 load, and does not prove cloud idempotence.

Preflight found two previously unexecuted fixture-definition errors. The
midnight SQL expectation declared only eight of the model's 27 columns; native
SQL expectations require the full output. It now uses supported partial expected
rows with the same intended values. The tie fixture's expected UNION branches
had different column counts; the cohort-only row now explicitly expects false
item-view and ordered-item-view flags. No business model SQL changed.

Ordinary `dbt compile --select test_type:unit` selected nothing with the pinned
version. The read-only [unit preflight adapter](../src/pipeline/dbt_unit_preflight.py)
uses the pinned native fixture loader/compiler and comparison macros, metadata
APIs, and BigQuery dry runs while forbidding adapter SQL execution:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- python -m pipeline.dbt_unit_preflight
```

All three comparison SELECTs and empty scratch CTAS preflights estimate zero
processed bytes. These are compilation/dry-run checks, separate from the real
native test passes. Errors and limitations remain under
`warehouse_builds.p2_5_tests.failed_preflight_attempts` and `.preflight_limitations`;
the successful estimates and hashes are in `p2_5_unit_preflight` in
[dry_runs.json](dry_runs.json).

Native dbt created three empty scratch tables, ran three synthetic comparison
SELECTs, and removed its scratch tables through the BigQuery table deletion API.
Complete inventory confirms no scratch relation remains and all seven persistent
relations/settings are unchanged. The six actual query jobs each processed and
billed zero bytes. Cleanup does not produce DROP_TABLE query jobs; it is not
misreported as query execution. Actual job IDs, caps, SQL hashes, fixture results,
cleanup checks and six passing relevant Python regressions are under
`warehouse_builds.p2_5_tests`. Native SELECTs match preflight comparison SQL after
ignoring comments and whitespace.

The first metadata-evidence save failed during atomic JSON serialization with
`TextIOWrapper.write() takes exactly one argument (0 given)`; the original
metrics file remained intact. Documentation was committed before that save was
confirmed, then corrected in a follow-up evidence commit. Metadata checks were
repeated without rerunning tests; a small standalone record was saved and merged
in a separate local process, then read back and validated. The cause remains
unconfirmed; `.evidence_writer_incident` records the failure and recovery.

P2.5 is complete. Full actual catalog generation remains P2.6 within the same
bounded approval; all other owner gates remain unchanged.
