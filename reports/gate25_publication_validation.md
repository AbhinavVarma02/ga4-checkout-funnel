# Historical CI checksum false positive

This records a failed full-history scan and its verified checksum false positive.
Source: `warehouse_builds.p5_9_gate25_publication` in [metrics.json](metrics.json).
The later successful ordinary CI checkpoint is recorded in
[manual workflow evidence](manual_workflow_native_validation.md).

## Actual ordinary CI result

[CI run 37552301418](https://github.com/AbhinavVarma02/ga4-checkout-funnel/actions/runs/37552301418)
was triggered by `push` on `main`, exact SHA `5ca393c`, attempt 1. It ran
2026-10-07 00:30:13–00:31:37 UTC and completed **failure**.
The `checks` job's installation, Python/SQL lint, unit tests, report rebuild/
reproducibility and credential-free dbt parse all succeeded.
**Scan full Git history for secrets** failed; no workflow was rerun.

The CI scan reports 140 commits and one finding. Its default console output
does not identify the finding. Read-only native `gh run view --log-failed`
retrieved the redacted failed-step log after direct job-log requests failed.
The already cached, checksum-verified Gitleaks 8.30.1 executable reproduced
exactly one finding over the same 140 commits/15,397,733 scanned bytes:

```text
568d12c0bb3a9b4a8b8ffe07beb927acf3837d98:reports/metrics.json:generic-api-key:26464
```

This identifies historical JSON field
`continuation_validation.p5_6_gate20_recovery_proposal.diagnosis.execution_api_auth_log_sha256`.
Its 64-character hexadecimal value exactly matches the SHA-256 of the retained
`reports/.checks/p5_6_backfill_run/gate19_native_2021-01-18/dbt_build_attempt_1.log`.
It is a verified log checksum, **not an API credential**. Neither that raw log
nor any key/secret value was displayed. Redacted finding and checksum proof are
retained separately.

## Exact-fingerprint remediation

The checksum/source path was independently verified as noncredential evidence.
A temporary exact commit/file/rule/line exception passed the same pinned scan
with zero findings and exit zero. The historical failing CI result remains
recorded; the subsequently published narrow exception and successful ordinary
CI 37555548304 at fe4d683 are separate checkpoints. No broad rule/path exclusion
or alteration of canonical query/accounting values is used.
