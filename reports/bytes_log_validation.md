# P5.5 native accounting: completed and verified

The owner replied `go` to the exact [accounting command/scope](bytes_log_validation.md).
The CLI exited 0, executing one uncached US metadata SELECT capped at
67,108,864 bytes (64 MiB), then writing [bytes_billed.csv](bytes_billed.csv).
Actual job IDs, parameters, SQL/hash, result rows, CSV row/hash and preservation
checks are saved under `warehouse_builds.p5_5_native_accounting` in
[metrics.json](metrics.json).

The native SELECT's 30 job IDs exactly match the independent completed-job API
inventory for `owner_replay_20201101_rerun`, within the approved UTC window
2026-10-05T20:43:55 to 20:44:44. Nine script children are included and three SCRIPT
summaries are excluded, preventing parent/child double counting. The two
snapshot jobs have a different label and are outside this run row.

| Verified CSV measure | Actual value |
|---|---:|
| Rows | 1 |
| Query jobs | 30 |
| Processed bytes | 52,964,097 |
| Billed bytes | 220,200,960 |
| Failed jobs | 0 |
| Fresh metadata dry-run estimate | 1,126,246 |

The CSV is 232 bytes; its SHA-256 is
`e743075d2db30145a83db394a0a503c8e0ce06ea7f700575c491ea7572832638`.
It was absent before execution, so no existing CSV rows were overwritten.
The native CRLF bytes and SHA-256 now match the committed Git blob exactly.
A report-only Git attribute preserves these bytes across checkouts; an explicit
index refresh corrected the initially normalized/cached LF entry without
repeating a query or recalculating the row.
Local upsert/legacy/failure fixtures remain separate evidence and incurred no
query charges.

The lookup itself is job `dd27c61a-bd5e-4289-a903-8d1b5196155c`:
DONE, SELECT, no error, US, uncached, with the approved parameters/SQL and
64 MiB cap. It processed **21,742 bytes** and billed **20,971,520 bytes (20 MiB)**.
Its labels are `app=ga4_checkout_funnel` and `role=bytes_log`, without the
selected `ga4_run`; it is intentionally outside the run CSV and recorded
separately in metrics. The earlier preflight estimate was 779,268 bytes; the
fresh estimate remained below the cap. Estimates are not actual billed bytes.

At the previously recorded $6.25/TiB rate, actual lookup bytes imply gross query
cost **$0.000119209**, and the existing logged dbt run implies **$0.001251698**,
before allowances/credits. These are byte-based calculations, not invoice or
account spend. Storage is additional and account-wide allowance/spend is unknown.
This row covers the dbt rerun only; it is not an end-to-end daily pipeline cost.

Existing raw, analyst and replay metadata are unchanged. All starting metric and
dry-run values, all 300 owner Power BI files' bytes/index/status, canonical CSVs
and offline report bytes are preserved. Automatic resubmission of a failed
lookup query job is disabled; nine recorder tests and all **183 Python tests**
pass in an isolated snapshot using tracked Power BI definitions. Python lint and
formatting (65 files), five export/wording checks and 224 relative links pass.
All 108 reachable commits through c133cea pass the pinned Gitleaks scan with zero
unresolved findings and the existing exact noncredential exception unchanged.
The final evidence commit follows that scan. No new remote CI or Desktop
rendering is claimed.

P5.5 and Needs from human #14 are complete for this bounded native CSV proof.
Native Airflow failure accounting, runtime/identity, scheduling and 92-day
backfill remain P5.6. Docker's wrapper exists but the read-only `docker ps` probe
still fails because WSL integration is unavailable. The brief requires recording
owner startup/integration under #13 instead of attempting Docker repair.
No further charged query, raw load, dbt build, Airflow task, backfill, IAM/workflow,
push, tag or owner-file deletion was executed. The historical command requires
a new scoped go before repetition.
