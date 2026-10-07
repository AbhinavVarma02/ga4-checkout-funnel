# Local historical replay scheduler

This pinned Docker/Astro project runs a simulated historical GA4 feed. The DAG
starts paused, automatic catchup is disabled, and maximum active runs is one.
Extraction → source/raw reconciliation → dbt compile/preflight/build feeds an
`all_done` byte logger; `finish` requires every data task and logging to succeed.

The [runtime](../reports/airflow_runtime_validation.md),
[first native run](../reports/airflow_first_day_validation.md),
[failure](../reports/airflow_failure_validation.md),
[recovery](../reports/airflow_recovery_validation.md), and
[92-day completion](../reports/airflow_gate23_validation.md) retain actual evidence.
The image is Runtime `3.3-8-python-3.12`, Airflow `3.3.2+astro.1`.

From the repository root:

```bash
cp -n airflow/replay.env.example airflow/.env.replay
make airflow-up
```

Configure the ignored replay file for your project, isolated US raw/analytics
datasets, read-only ADC, and a positive byte cap. Stack startup is local; unpausing
or submitting tasks/backfills can create warehouse resources and incur charges.
Existing `.env`, Airflow connections/settings, and persistent volumes should be
retained. The empty `replay-settings.yaml` avoids importing settings implicitly.

The Compose override mounts the project and gcloud configuration read-only for
credentials. Its named WSL account is UID 1000 with its own writable home; other
host UIDs need a matching named account before use. The DAG processor retains
Astro's original user for existing logs. Credential permissions are not changed.

The replay example's 128 MiB per-query cap covers bounded first-day validation;
it is not a full-history budget. The recorded full backfill used a 4 GiB query
cap. [Cost planning](../reports/backfill_cost_review.md) distinguishes dry-run
estimates, scripts/tests/retries, actual labeled bytes, and unverified account costs.

The installed backfill CLI supports date inspection without a load:

```bash
cd airflow
astro dev run backfill create --dag-id ga4_daily --from-date 2020-11-01 \
  --to-date 2021-01-31 --reprocess-behavior none --max-active-runs 1 --dry-run
```

For the completed replay, all 92 task dates succeeded. Native task retries and
reused first-day history are retained. Recovery labels include actual UTC start,
and CSV keys include the window because native non-partitioned reprocessing can
reuse a DagRun identity. The diagnostic boolean fails reconciliation's task only
after its real source/raw check succeeds; logging still runs and preserves a failed
DagRun. See [replay semantics](../docs/replay_design.md) and the [runbook](../docs/runbook.md).
