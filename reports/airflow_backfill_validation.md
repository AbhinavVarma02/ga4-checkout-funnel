# Gate #18 Airflow backfill validation

This is the **historical Gate #18 stopped checkpoint**. Owner go #19 subsequently
resumed the existing backfill and stopped again on a native heartbeat retry;
[Gate #19 validation](airflow_gate19_validation.md) records the latest state.
All original Gate #18 values below remain unchanged.

Historical status: **STOPPED at the monitoring-loss gate; resume #19 was pending**.
The DAG is paused and its scheduler is frozen. The host monitor disappeared after
76 verified dates; the tool reported an unknown process ID, an independent PID
probe found no observer, and live snapshots stopped updating. The underlying
cause is unconfirmed. Manual stop commands both succeeded. No task was cleared,
no second backfill was submitted, and no resume occurred.

Retrospective free job/result/metadata APIs establish the complete submitted
inventory: **2,801 actual job records**, terminal without errors,
with **276,061,749,248 cumulative billed bytes
(257.10254 GiB)** including partial January 18 work.
**The 512 GiB hard stop was not reached.** These are query bytes, not an invoice;
remaining allowance, credits and storage/other costs are unknown.

Source: `warehouse_builds.p5_6_full_backfill_checkpoint` in [metrics.json](metrics.json).
The ledger excludes SCRIPT parent summaries and includes their children and
separate logger lookups. It retains the original approval window for any future
resume. All cached completed values were audited through native APIs.

## Completed work and preserved state

One reprocess-none submission created backfill **4**, with **91 new DagRuns**.
The native linkage marks the original successful November 1 run “already exists”;
its run identity, start/label and all five task records are unchanged.

**77 new dates November 2–January 17 succeeded**, each with all five tasks on the
first attempt, seven models/fourteen data tests, all eight source/raw signals equal,
and exact independent job/result/CSV accounting. Totals are **385 successful tasks,
539 successful model results and 1,078 passing native data tests**. All three actual
replacement date arrays were retrieved from completed SELECT child results and
bounded to loaded sample dates. Full-window row fingerprints and injected late
events were not tested. The last shared dbt artifact had advanced to January 18;
January 17 success is instead proved by immutable native logs and completed jobs.

**January 18 is frozen in progress; January 19–31 are queued**. Thus **14 dates
remain unfinished**. Raw metadata has **79 populated partitions** because January
18 extraction completed. The active day's models/queries are partial; terminal
BigQuery jobs do not establish a successful active task/DagRun. **81 CSV rows**
contain four preserved historical receipts and 77 independently verified new rows.
The ledger additionally includes the active day's already submitted query bytes.

All **300 owner Power BI files**, bytes/index/status, owner configuration, original
metrics/dry-run values and CSV receipts, canonical exports and the offline report
are preserved. Analyst warehouse full metadata is unchanged. Raw/fact creation
times, schemas, DATE partitioning, clustering and expiration settings are retained;
only approved raw/replay data changed. All job caps stayed within the approved
4 GiB US isolated scope, and no extra paid verification query ran.

## Prepared repair and next gate

The detached monitor launcher and independent watchdog have durable log/PID
receipts and a fresh heartbeat barrier. Dead/stale observation or a missing peer
stops work; signal termination follows the same stop path. Workers freeze before
DAG metadata is paused through the separate API server. Native state and immutable
logs can be inspected while the scheduler remains frozen. The original cumulative
512 GiB accounting window is retained across process restarts and tested at its boundary.

**246 isolated tests / 56 focused guard cases pass**, with Python lint and **121
formatted files**. Detached-child survival, dead peer/stale heartbeat, malformed
accounting, cached cumulative boundary, signal, frozen log/native read, and
freeze-before-metadata-pause checks pass. Actual frozen native reads/log capture
and idempotent stop are verified. The earlier unchanged SQL lint evidence remains
valid. The launcher/watchdog were **not activated**, and real resumption is untested.

The [exact required Gate #19](airflow_gate19_validation.md) covers resuming
existing backfill 4's January 18 task and January 19–31 queue, with unchanged caps,
targets and the cumulative checkpoint. It authorizes no new submission or clear.
docs/runbook.md and Gate #18 require another reviewed go after this stop. P5.6 remains
incomplete; P5.7 paid comparison, IAM/workflow, push/tag and owner acceptance remain gated.

## Earlier immutable eleven-day checkpoint

This immutable checkpoint was recorded at **2026-10-06T00:51:28.822789+00:00**.
Its source key is `continuation_validation.p5_6_gate18_test_checkpoint` in
[metrics.json](metrics.json); ignored native job/results/log artifacts and their
hashes are recorded there. Later work can advance beyond this dated prefix.

## Verified completed prefix

**11 new dates**, November 2–12, each have all five tasks
successful on their first attempt, seven successful dbt models, fourteen passing
native data tests, and all eight source/raw signals equal. The completed logger
result IDs and bytes agree with the independent leaf-job inventory. SCRIPT
children are included and their parent summaries excluded.

| Date | Raw/source events | Purchases | Purchase revenue USD | Leaf billed bytes |
|---|---:|---:|---:|---:|
| 2020-11-02 | 48,388 | 49 | 4789 | 335,544,320 |
| 2020-11-03 | 61,672 | 49 | 3313 | 441,450,496 |
| 2020-11-04 | 51,866 | 46 | 2197 | 515,899,392 |
| 2020-11-05 | 51,952 | 26 | 1792 | 596,639,744 |
| 2020-11-06 | 49,004 | 58 | 3438 | 675,282,944 |
| 2020-11-07 | 34,309 | 31 | 2531 | 719,323,136 |
| 2020-11-08 | 30,137 | 32 | 3760 | 763,363,328 |
| 2020-11-09 | 44,756 | 52 | 2154 | 849,346,560 |
| 2020-11-10 | 51,195 | 64 | 4041 | 939,524,096 |
| 2020-11-11 | 51,941 | 64 | 4428 | 1,024,458,752 |
| 2020-11-12 | 49,166 | 54 | 3349 | 1,099,956,224 |

The verified prefix totals **6,373,462,413 processed** /
**7,960,788,992 billed bytes**. Its separate logging
lookups processed/billed **0 / 0 bytes**.
The live monitor observed **9,875,488,768 billed bytes** at
**2026-10-06T00:51:20.804670+00:00**, including jobs from current in-progress work.
This differs from completed-prefix totals for that reason.

## Local checks and preservation

All **227 tests** pass in an isolated current-source/tracked-Power-BI snapshot,
using the previously documented allocator workaround. Python lint passes;
**118 files** pass formatting. Standalone/fixture SQL lint and offline dbt
compilation lint pass; the latter checked **8 SQL files** with **0 violations**
and warehouse connections forbidden. Result collection uses existing completed
job/result APIs with SQL/mutations blocked and automatic job retry disabled.

All **300 owner Power BI files**, their bytes/index/status, owner configuration,
canonical CSV exports, the offline report, old metrics/dry-run values, and the
four pre-existing billed-byte CSV rows are preserved. The documented Astro start
rebuilt the local application image; mounted DAG source and pinned runtime/package
versions were verified unchanged, with existing PostgreSQL/log volumes retained.
Actual scheduler and dbt query caps are **4 GiB** in US isolated raw/replay targets.

The monitor pauses the DAG and freezes its scheduler on any stop. At the 512 GiB
checkpoint it returns before further evidence/validation work. Already submitted
cloud jobs can finish; no automatic resume or cap increase is authorized.
On complete success it pauses the DAG again. Full-window totals/partition proof
remain pending. This checkpoint establishes no invoice, remaining account-wide
free allowance, recurring production operation, native late-event injection, or
full-row parity. P5.7 paid cost comparison, IAM/workflow, push and tag remain gated.
