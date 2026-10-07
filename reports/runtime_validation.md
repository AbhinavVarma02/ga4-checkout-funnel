# Human Step #8 runtime and history validation

Human Step #8 is complete. The repository started clean on `main` at
`8a7b8ba4bb713fdc25f1d48e615eb56bdf28feee`, after the completed Step #9 scope.
Both documented checks passed on 2026-10-05 UTC (2026-10-04 owner local date).
Actual results, source/image/log hashes, timestamps, the failed initial attempt,
and scope checks are saved under `human_step8_validation` in
[metrics.json](metrics.json). Earlier metric sections and all five BI CSV hashes
are unchanged.

The exact validation commands were:

```bash
cd airflow
astro dev parse
cd ..
docker run --rm --network none -v "$PWD:/repo:ro" -w /repo \
  ghcr.io/gitleaks/gitleaks:v8.30.1 git --redact /repo
```

The first Astro attempt failed before validation because Docker Buildx could not
write its activity file under the sandbox's read-only `~/.docker` directory.
The owner-approved filesystem escalation repeated the same command successfully.
Astro CLI 1.46.0 reported Runtime 3.3-8, Python 3.12.14 and one passing real
Airflow DagBag integrity test with no DAG import errors. It used the current
edited failure-logging/catchup-disabled DAG; its source SHA-256 is
`fe5010a7935d5b427e4008f5ab6f24959c2fcb77c0a06158ef81c34ff0ceaf66`.
The command exited zero. Three grpcio/PQC deprecation warnings and one pytest
cache permission warning were reported. No dependency pins were changed.
Evidence: `human_step8_validation.astro_parse`.

The pinned Gitleaks image was already present, so no pull was needed. The scan
exited zero, scanned all 75 reachable commits through the baseline commit, and
reported no leaks. Networking was disabled, the repository mount was read-only,
and output was redacted. This scan ran before the evidence/documentation commit;
the saved commit identity defines its coverage precisely.
Evidence: `human_step8_validation.gitleaks`.

Actual command logs remain ignored under `reports/.checks/step8/`; their hashes
are saved in metrics.json. The successful Astro log is
`astro_parse_escalated.log`, the initial failure is `astro_parse.log`, and the
history scan is `gitleaks.log`. These container results supersede the earlier
pending runtime/scan statements while preserving those historical checkpoints.

An Astro stack, including a scheduler, was already running before this task.
Its scheduler container identity, creation/start timestamps, restart count and
running status match the recorded baseline after both checks. No scheduler was
started or restarted, no DAG was unpaused, and no task, cloud query, raw load,
replay, backfill or billing action was submitted. Runtime pause/run state was
not queried; the source still declares `is_paused_upon_creation=True` and
`catchup=False`. No owner file was deleted, and no remote push or release occurred.
Evidence: `human_step8_validation.boundary_verification`.

This verifies current DAG imports, not task execution, actual scheduling,
cloud failure accounting or JOBS_BY_PROJECT permissions. P5.6 remains blocked
on separately approved backfill/runtime execution; P6.4 remains blocked on the
remaining cloud, Power BI, CI and owner-review requirements. Work stops before
all remaining owner gates.

## Prior P5.6 local checkpoint

The section above records the historical Human Step #8 snapshot. The later
[current runtime validation](airflow_runtime_validation.md) now verifies the
current DAG and corrected local user/configuration, healthy paused stack,
92-date dry listing, SDK callback fixtures and actual scheduler read-only
metadata/compile/dry-run access. No cloud task instance or backfill has executed.
Source: `continuation_validation.p5_6_airflow_runtime` in metrics.json.

## Subsequent native integration and failure preparation

The separate #15 go completed [one actual first-day Airflow run](airflow_first_day_validation.md). The current diagnostic has [local/native SDK preparation evidence](airflow_failure_preparation.md), while its failed-run/recovery execution remains [separately gated](airflow_failure_validation.md). The DAG is paused again; no full 92-day backfill has executed.
