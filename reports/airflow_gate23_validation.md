# Gate #23: January 31 completed; all 92 sample dates successful

Status: **COMPLETE.** Existing backfill **4** is complete, with **91 new successful
dates** plus the unchanged original November 1 run. All **92 DagRuns / 460 task
rows** are successful. The DAG is paused, scheduler workers are idle, both guards
have exited, and container identities/restart counts/volumes are preserved.

Source: `warehouse_builds.p5_6_gate23_completion` in [metrics.json](metrics.json),
including `final_validation`, `full_window_native_summary` and
`january31_exact_lookup`. The approved [Gate #23 scope](airflow_gate23_validation.md)
executed at **`554a3bdb5b21de9809cd462ab8ae7350e6b8dc29`**.

## Exact recovery and native quality

Preparation verified the existing retired January 31 UUID
`01a112b6-0a88-7b93-bee3-6f0c9ddc5fa4`, null/counter 1, failed original UUID/history,
fixed heartbeat/orphan events and exact saved terminal-log SHA. It preserved the
94-row CSV and original preflight in immutable copies. No generic SIGTERM
exception, task clear/state repair, new backfill or upstream rerun was introduced.

Fresh guards were ready before worker unfreeze at **2026-10-06 19:59:48.628263 UTC**.
The DAG stayed paused while old process births remained gone and all executors
remained idle. Drain readiness was recorded at **19:59:51.081800 UTC**, and the
guarded DAG unpause completed at **19:59:55.798274 UTC**, **4.716474 seconds** later.
Only the one approved fresh dbt attempt 2 and original logger/finish dispatched.

| January 31 task | Final native state / counter |
|---|---|
| extract_day | success / 1, unchanged |
| reconcile | success / 1, unchanged |
| dbt_build | success / 2, same rotated UUID |
| log_bytes | success / 1 |
| finish | success / 1 |

The native dbt log reports **seven successful models, fourteen passing data tests,
PASS=21 WARN=0 ERROR=0 SKIP=0 TOTAL=21**, and the January 31 replay-build success
marker. All five task logs/actual counters are saved. The original failed attempt
log/history remains intact. The DagRun succeeds at **20:00:49.817398 UTC** with
its original ID **92**, start **17:04:33.601315 UTC**, original run ID/label/window.
The monitor completed and paused the DAG again at **20:01:18 UTC**; backfill 4's
normal completion metadata was subsequently recorded without changing its scope.

All earlier completed/upstream rows and ten earlier history records remain
unchanged. January 18/19 dbt attempt 2 successes and their failures are retained.
The reused November 1 history also remains unchanged: extract/reconcile/logger
counters **3**, dbt/finish counters **2**, from its separately approved earlier
failure/recovery. Within the 91 new backfill dates, only January 18/19/31 dbt
has counter 2; all other tasks are first-attempt successes.

Saved native quality evidence covers all **91 new dates**: **637 model successes
and 1,274 data-test passes on their successful attempts**. January 18's proof uses
its separately saved Gate #19 attempt-2 log; other dates use their immutable
native summaries. Historical failed attempts are not relabeled as successes.

## Reconciliation, selectors and exact receipt

Existing-result APIs independently revalidate January 31's eight source/raw
signals. Both sides contain **26,489 events / 19 purchases / 19 purchases with
transaction IDs / one distinct transaction ID**. Purchase revenue count is zero
with total **null**; USD purchase revenue count is 19 with total **0**. These are
the observed obfuscated-data values, with null and zero preserved distinctly.
No reconciliation SQL was repeated. Raw still has **92** loaded partitions.

All five January 31 SCRIPT selectors across both attempts are retained: two old
session/product scripts and three fresh fact scripts. Each selects exactly:

```text
2020-12-28, 2021-01-12, 2021-01-20, 2021-01-29, 2021-01-30, 2021-01-31
```

These are the normal affected session-start partitions within loaded history.
The fresh attempt replaces all three facts and performs only normal cleanup of
its own temporary relations. The two older January 19 orphaned temporaries remain.
No manual table/file/volume deletion or analyst-dataset write occurred.

January 31's native lookup **`d3e0beec-aa86-4ebb-b5e6-e62220eb3cc2`** contains
exactly the same **48 leaf IDs** as the independent API inventory, covering both
attempts and upstream work in the original label/window. Per-job and total byte
statistics agree: **12,915,087,102 processed / 13,073,645,568 billed bytes**, with
zero failed query jobs. SCRIPT parents are excluded; children count once. Its
separate lookup processed **318,725** and billed **20,971,520 bytes**, included in
cumulative accounting. All 48 native lookup rows and independent IDs are saved.

The CSV has **95 rows**, with one new January 31 receipt. The native recorder
inserts it in its usual sorted position: removing that one physical line restores
the exact original **94-row bytes and order**. Their archived SHA-256 remains
`990d1cd0232b04dfe337ecc9b5a64c7c0354e9e5d231d4b626204fefb9f99508`.
January 30's native **31-job** row/lookup remain unchanged; its exact saved
one-zero-byte-record supplement reconstructs all **32** API leaf IDs. No other
date receives that exception, and January 31 matches strictly.

## Final accounting, metadata and limits

Independent final job-list metadata agrees with the cumulative cache. All
**3,337 submitted records** are terminal without query errors; all **3,303**
pre-Gate-23 records remain exact. **34 new records** belong only to January 31's
original label. SCRIPT parent/child processed and billed totals reconcile.

| Measure | Actual value |
|---|---:|
| Cumulative billed bytes / GiB | **381,591,486,464 / 355.384765625** |
| Gate #23 added bytes / GiB | **7,076,839,424 / 6.5908203125** |
| Gate #23 gross query arithmetic, saved $6.25/TiB | **$0.0402271747589111328125** |
| Original cumulative stop / query cap | **512 GiB / 4 GiB**, unchanged |
| Remaining headroom bytes / GiB | **168,164,327,424 / 156.615234375** |
| Completed sample dates / new backfill dates | **92 / 91** |
| Final CSV rows / submitted job records | **95 / 3,337** |

Costs cover the original backfill accounting window, not all account charges or
an invoice. Free allowance, credits and storage/other costs are not inferred.
Actual Gate #23 usage includes its lookup and exceeds the saved adjacent-date
6.5390625-GiB proxy; that proxy was never a bound.

Raw and analyst warehouse metadata are unchanged. Replay schemas, partitioning,
expiration settings, fact creation metadata and retained temporary relations are
preserved. The approved repeated dbt build normally recreates `dim_date` and its
three views: their creation timestamps fall within the fresh attempt; view SQL
hashes and schemas match the previous January 31 definitions. An initially overly
strict read-only audit compared those four timestamps as immutable; it was
corrected to validate this normal build behavior and rerun through free APIs.
No runtime controller change or additional activation followed completion.

Owner Power BI file bytes/index/status, configuration, task sources, canonical
exports/report and all previous metric values are preserved. All other old
artifact hashes remain unchanged; only the cumulative cache, current CSV and
new metrics evidence advance. The original January 31 preflight is archived,
and its current report retains the actual fresh dry-run timestamps/estimates.
All three container identities, zero restart counts and named volumes are intact.

All **192 focused tests** and changed Python lint/format checks passed before
execution. No full suite or extra SQL/dry run was submitted for collection/audit.
Full-window native row fingerprints and deliberately injected late events were
not tested. Actual source/raw equality, quality passes, affected-date selectors
and accounting are the verified scope. This completes **P5.6**; **P5.7** cost
comparison, IAM/manual cloud workflow, final release acceptance and tag/push remain
separate scopes. No next phase was activated.
