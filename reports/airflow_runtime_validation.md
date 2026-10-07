# P5.6 prior local Airflow/Astro validation

This report records the #13 local checkpoint before the first-day owner go.
At that checkpoint the DAG was paused, with **zero DAG runs, backfill records and task instances**.
No cloud SELECT execution, load, warehouse mutation or non-dry backfill occurred.
Evidence source: `continuation_validation.p5_6_airflow_runtime` in
[metrics.json](metrics.json). P5.6 remains incomplete until separately approved
native task/failure-accounting and full-window execution evidence exists.

The owner confirmed Docker Desktop/Ubuntu WSL availability and authorized local
validation while explicitly withholding backfill execution. Docker client/server
29.8.1, Desktop 4.93.0 (240920), and Astro CLI 1.46.0 were observed. Astro Runtime
3.3-8 / Python 3.12.14 and the existing dependency pins remain unchanged.
The validated project image ID is
`sha256:84864190110a28363fdaf9455a50d3202b1a89432589bb0b4051c56e46505b4e`;
the unchanged DAG source SHA-256 is
`996fe737a0b2f1a764837558438e8ccddcc7f9fd1fcef9bef45bfeeb709405c5`.

The existing scheduler was exited with code 127 and source bind mounts were empty;
the exit cause was not established. Local refresh retained the named PostgreSQL
and Airflow log volumes, but replaced application containers and changed start
times. Root `.env`, existing Airflow env/settings and owner connections/pools/
variables were preserved. The independent ignored replay env selects US raw and
isolated replay destinations with a 128 MiB validation cap. Empty replay settings
prevent owner configuration imports, and fixed ports avoid the read-only Astro
proxy route lock.

Native access checks found the default scheduler UID could not read mode-0600 ADC.
The image now provides a named WSL UID-1000 account with a separate writable home;
the scheduler/LocalExecutor uses it with GID 0. ADC remains mounted read-only, with no permission
change or credential copy. The DAG processor retains its original Astro user for
existing log ownership. The first UID attempt failed because it lacked a username;
a subsequent compile exposed Astro's existing dbt cache ownership. The final
named account/home resolves both; no earlier failed attempt is counted as a pass.
Temporary temporary local writes verify access to task logs, reports and dbt
target/log directories; no owner file was changed. The verified configuration is in [airflow/README](../airflow/README.md).

Native checks passed:

- Astro DagBag import: one test, four recorded warnings; Buildx required approved
  filesystem escalation. Warnings concern grpcio's future minimum and pytest cache
  permissions; no dependency upgrade is claimed.
- Real installed SDK callbacks: nine cases with external I/O mocked and network
  disabled. They cover all five tasks, shared caps/labels, missing-XCom logging,
  reconciliation failure propagation, sample bounds, analyst target and cap guards.
- Related host regressions: 57 passed, no failures/errors/skips, under Python 3.12.15.
  The previous full 183-test checkpoint remains historical.
- Local API reports healthy metadata database, scheduler, triggerer and DAG processor.
  DAG import errors are empty; graph/retries/trigger rules match current source.
- Installed backfill CLI `--dry-run` lists all 92 dates from 2020-11-01 through
  2021-01-31. Installed source returns before backfill creation; the database still
  has no runs, backfills or task instances afterwards.
- Serialized `CronTriggerTimetable` produces the same 92 source dates via
  `data_interval_start.date()`. Its intervals are zero-length UTC-midnight
  intervals; a 24-hour interval is not assumed.
- Actual scheduler identity reads existing raw/replay/analyst metadata and the
  completed accounting job. Inventory, schemas, view hashes, creation/modification
  times, rows/bytes and expirations match the prior native checkpoint. API job
  listing reports no executed jobs created since the local baseline.
- Native container dbt compilation succeeds with adapter SQL execution blocked.
  All 43 submitted queries are dry runs: seven models at each of four representative
  dates, fourteen first-day data-test SELECTs, and one logger metadata SELECT.
  First-day model/test estimates total 174,986,425 bytes; every individual estimate
  fits the 128 MiB cap. Logger estimate is 1,142,001 bytes; no CSV was written.

[Container preflight](airflow_container_preflight.json) records date/model SQL
hashes and real estimates. Future-history planning substitutes public shards for
hypothetically loaded raw history; it is not a measurement of future raw tables
or generated DML. Seven-day planning already has one model above the current cap;
full-window staging estimates reach 2,891,550,912 bytes. The current validation
cap cannot authorize the full backfill. Scripts, child statements, tests, retries,
storage and account-wide allowance/spend need further execution-scope review.

All starting metric/dry-run values, canonical exports/offline report, native byte
CSV and owner Power BI bytes/index/status are preserved. Published results retain
their original source keys; these dry runs add no business result. Preservation,
local lint/link checks and final committed-history secret scan are recorded under
this checkpoint's source key. Pinned Gitleaks 8.30.1 scans all 110 reachable
commits through `1a351d1` with zero unresolved findings; the existing exact
historical noncredential exception is retained and this evidence commit follows
that scan. Implementation is committed at `1a351d1`. Raw logs/scripts remain ignored under
`reports/.checks/p5_6_runtime/`.

The next required cost-bearing gate is [bounded first-day Airflow integration](airflow_first_day_validation.md).
Actual scheduled task execution, native failure/recovery accounting, broader raw
history repair and the 92-day backfill remain unclaimed and separately gated.

## Subsequent checkpoints

The preceding section records local validation before #15. A separate owner go now completed [native first-day integration](airflow_first_day_validation.md). The next [failure/recovery gate](airflow_failure_validation.md) has [validated preparation](airflow_failure_preparation.md), with no failed run or recovery executed. Full-window execution remains independently gated; the DAG is paused.
