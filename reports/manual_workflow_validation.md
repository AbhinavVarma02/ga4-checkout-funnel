# P5.9 safe local preparation

Continued only P5.9 from `0b03c8087cf7cb8bcdf508e42e95197ebefbc7e4`.
P5.6, P5.7 and P5.8 remain complete. P4.3 acceptance/tagging and P6 work were
not advanced. Source: `continuation_validation.p5_9_manual_workflow_preparation`
in [metrics.json](metrics.json).

The previous manual workflow could rebuild the populated `ga4_analytics`
tables over the full window. It now uses a dedicated fixed US `ga4_ci` profile
and the November 1 public shard. Plan checks run before cloud authentication;
they reject changed project/location/cap/branch/repository/commit, nonmanual
events and workflow retries. An occupied target prevents accidental repeats.
The default confirmation remains `cancel`.

Seven models and fourteen data tests have compiled locally with BigQuery SQL
execution/client construction/connection opening forbidden. The native dbt
connection-close hook was suppressed solely to avoid opening a never-used lazy
connection during cleanup. An initial blocked compilation detected that cleanup
path; no connection or cloud SQL occurred. The reviewed compile command disables
introspection and schema-cache population and excludes native unit fixtures.

The actual compiled manifest and all twenty-one inlined SQL statements passed
the new preflight checks with a synthetic client. Synthetic zero estimates are
explicitly fixture values; **no native estimate or query result is claimed**.
That check caught dbt's default test audit-schema metadata: its unused name is
allowed only with persisted test failures disabled. Actual model destinations
and compiled dependencies remain constrained to `ga4_ci` and the public shard.
The final focused tests cover changed scopes, occupied/wrong-region targets,
oversized/unknown estimates, incomplete and failed API receipts, SCRIPT parent
exclusion, native result completeness, completed-node job ID membership
(including zero-byte jobs), pre-authentication planning and reruns.

Python lint/format and the complete existing `make lint` checks pass, including
raw SQL/fixtures and eight real sandbox dbt SQL files with warehouse connections
forbidden. YAML parses, workflow artifact paths form an explicit allowlist and
shell run blocks pass syntax validation. The full Python suite and report/BI
regeneration were not needed; the focused checks include sandbox/replay profile
regressions. Exact final test counts, command results and artifact hashes are
recorded in the source key above.

A fresh read-only `gh run list` for `dbt_bigquery.yml` returned `[]`.
The first sandbox attempt could not connect to GitHub; the approved read-only
network escalation succeeded. No workflow was dispatched or rerun. The older
ordinary green CI receipt at `c2c0241` remains historical evidence; it cannot
attest this preparation or its eventual publication.

All pre-existing metric values, completed backfill/accounting/comparison files,
95 CSV rows, canonical exports, owner configs and all 300 Power BI file hashes
plus git index/status are preserved. Only one new preparation section is added
to metrics.json. No Airflow/Docker action, SQL submission, warehouse write,
resource creation, IAM/key/secret change, push, tag or deletion occurred.
Combined recorded query usage remains **355.4794921875 GiB**.

**P5.9 remains BLOCKED** on the separate [setup gate #4](manual_workflow_native_validation.md)
and later publication/cloud execution gate #25. Local preparation is reviewable
and committed; native workflow success, identity/permissions, estimates, bytes
and new warehouse state remain pending.
