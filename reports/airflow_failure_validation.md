# P5.6 native controlled failure and accounting repair

Status: **native task failure/logging verified; recovery withheld at gate #17**.
The owner approved [gate #16](airflow_failure_validation.md). Its diagnostic command
executed for 2020-11-01 only. Source: `warehouse_builds.p5_6_controlled_failure`
in [metrics.json](metrics.json). The DAG is paused again.

The real extraction and eight-signal source/raw reconciliation succeeded. The
reconciliation callback then raised the explicit SDK `AirflowFailException`.
dbt and the final status task became upstream_failed; the all_done byte logger
succeeded and the DagRun remained failed. Actual reconciliation still agrees
on 31,272 events, 14 purchases and 773 USD purchase revenue. No deliberate data
corruption or failed SQL query occurred.

The installed non-partitioned backfill path invokes `_handle_clear_run` for
an eligible existing run. It resets task state and updates the existing DagRun's
backfill/configuration; its start time changes when execution begins. In this
actual run, DagRun ID 1 and `backfill__2020-11-01T00:00:00+00:00` were reused.
Backfill ID 2 was created. Three executed task counters rose from 1 to 2, each
representing one new attempt; dbt and finish counters did not advance. No retry
of the deliberate failure or dbt execution occurred. Installed source, before/
after state, native attempt logs and hashes are saved in the source key.

The original label used only run ID, so the failed execution reused
`ga4_5f05b5f984a3facd2730de02`. The logger's time window correctly selected only
the two newly completed queries, but the old `(label, date)` CSV key overwrote
the prior successful execution's row. This failed gate #16's preservation/
identity expectations. Its explicit stop-before-recovery condition was honored;
no recovery or further native cloud execution was submitted.

| Failed-execution accounting | Actual value |
|---|---:|
| Completed labeled query jobs | 2 |
| Processed bytes | 24,685,170 |
| Billed bytes | 45,088,768 |
| Failed SQL query jobs | 0 |
| Separate lookup processed / billed bytes | 0 / 0 |

The native row and lookup result IDs/totals match independently inspected
completed-job APIs. The lookup's zero bytes and cache_hit=false are API-reported
values for that job only. All executed queries used the approved 128 MiB cap.
Actual query bytes do not establish account spend or a zero-cost guarantee.

The repair derives future DAG labels from run ID and timezone-normalized actual
start time, keeping retries together while distinguishing reprocessing. CSV
records now also use `window_start_utc` in their upsert key. The reader accepts
both older headers and preserves their values; unknown historical window starts
remain `not_recorded`. Repeating a write for the same UTC window stays idempotent.
Equivalent timestamps in different timezones normalize to one identity.

Both original CSV rows were restored from the verified pre-execution receipt.
The failed row is retained separately, with its actual native lookup window.
The prior first-day start is sourced from its saved actual Airflow state. The
older manual row keeps `not_recorded` for its previously absent window field.
The report now has three rows, with every original eight-column value preserved.
This was a local migration/recovery of saved evidence, with no new SQL submitted.

Validation checks and hashes are recorded in metrics.json. Native SDK fixtures
run without networking and with external I/O mocked; they verify the repaired
identity's behavior but do not claim a repaired native cloud write or recovery.
The initial full-suite offline compiler subprocess exited with signal 11;
its logs are retained. A focused retry and full-suite recheck use the project's
existing `PYTHONMALLOC=malloc` workaround. The native crash's root cause remains
unconfirmed; no dependency pin was changed.

All starting metrics/dry-run values, canonical exports, offline report, owner
configuration and 300 Power BI files/index/status are preserved. Analyst
warehouse metadata and raw/replay inventory, schemas, counts, bytes and
expiration settings are unchanged; raw still has only partition 20201101.
No extra paid snapshot ran, so no new full-row equality proof is claimed.
Full-window execution, cost comparison, IAM/workflow, push and tag remain gated.

All 202 isolated tests pass with the documented allocator workaround; 79 related
host tests, 15 network-disabled SDK checks, one native import test and lint/format
pass. The pinned checksum-verified Gitleaks 8.30.1 scan passes all 115 reachable
commits through `141b055` with zero unresolved findings. The existing two exact
noncredential exceptions remain unchanged; no broader exclusion is added. Final
scan metadata evidence follows in a local commit.

## Subsequent separately approved recovery

[Gate #17 recovery](airflow_recovery_validation.md) now verifies the repaired native write path and fourth CSV row. Its later evidence is warehouse_builds.p5_6_airflow_recovery. Original failure metrics and this checkpoint remain historical; the gate #16 stop was honored. The DAG is paused with its reused run now successful and three completed backfill records. Full-window execution retains a separate cap/cost/allowance go.
