# P5.2 first-day extraction: completed and verified

Completed on 2026-10-05 after the owner's separate `go` to the exact command and
scope below. Only US `ga4_raw`/`ga4_events` were created and only partition
`20201101` was loaded. The table and partition have **31,272 rows** and
**23,503,520 logical bytes**. Source-derived schema, expiration, partition and
all eight source/raw reconciliation checks pass. Work stops at P5.2.

All numbers below are recorded from actual output or explicitly labeled cost
calculations in `reports/metrics.json`, `warehouse_builds.p5_2_raw_extraction`.
Its `preflight` retains the before-approval checkpoint; `before_load`, `execution`
and `verification` record the approved native run. Exact dry runs and real job
bytes are also saved in `reports/dry_runs.json`, `p5_2_20201101_*`.
Canonical business metrics and all prior evidence values are preserved.

## Actual executed jobs and reconciliation

Each query ran in US with cache disabled and a 33,554,432-byte cap, after its
successful dry run. Metadata APIs verify exactly these three completed jobs
under `ga4_run=owner_20201101`: one load and two read-only verification SELECTs.

| Operation | Dry-run bytes | Processed bytes | Billed bytes |
|---|---:|---:|---:|
| Extraction into `$20201101` | 23,566,064 | 23,566,064 | 24,117,248 |
| Partition metadata | 10,485,760 | 10,485,760 | 10,485,760 |
| Source/raw reconciliation | 1,119,106 | 1,119,106 | 20,971,520 |
| Total executed bytes | — | 35,170,930 | 55,574,528 |

Job IDs, in table order:

```text
5607541a-c573-4ea7-88ef-4b3e382a1f23
p5_2_20201101_partitions_7ea9ee83-65e9-49ac-9bb7-dd6ac7ff3bb2
p5_2_20201101_reconciliation_d1e72ba3-490c-411d-a239-b0f0b57d5bff
```

All jobs are DONE with no error. Actual load configuration names only
`ga4-checkout-funnel.ga4_raw.ga4_events$20201101`, uses `WRITE_TRUNCATE` and
`CREATE_NEVER`, and its SQL names only the physical `events_20201101` shard.
Actual partition metadata returns exactly one partition, `20201101`, with
31,272 rows and 23,503,520 logical bytes in ACTIVE storage. Table metadata agrees.
US location, daily DATE partitioning on `event_date`, `event_name` clustering,
null dataset expiration defaults and null table/partition expiration are verified.
All 23 top-level/108 total schema fields match recursively in name, order, type,
mode and nested shape, with only the approved STRING-to-DATE conversion.

| Reconciliation field | Source | Raw |
|---|---:|---:|
| event_count | 31,272 | 31,272 |
| purchase_count | 14 | 14 |
| purchase_with_transaction_id | 0 | 0 |
| distinct_transaction_ids | 0 | 0 |
| purchase_revenue_count | 14 | 14 |
| purchase_revenue_total | 773 | 773 |
| purchase_revenue_usd_count | 14 | 14 |
| purchase_revenue_usd_total | 773 | 773 |

Transaction-ID coverage is zero in the source on this day and remains zero in
raw. This is a preserved source limitation. No rows or values were repaired.
The DATE query parameter and complete actual query text are saved with job
evidence; no other date was loaded.

The actual billed-byte total implies **$0.0003159046173095703125** gross query
cost at the verified US on-demand rate, before free allowance/credits. Measured
raw logical bytes project **$0.0005034552514553070068359375/month** storage at
$0.023/GiB-month before free allowance. Storage is a projection; billed-byte
counters are not an invoice or measured credit consumption. Total project spend
and account-wide remaining free allowance remain unverified. This incremental
operation fits comfortably within $5, with gross query cost plus a full month
of projected storage under $0.001.
[Google pricing](https://cloud.google.com/bigquery/pricing).

## Verified preflight checkpoint

| Read-only check | Actual result |
|---|---|
| Configured/live project | `ga4-checkout-funnel`, lifecycle `ACTIVE` |
| Billing | Enabled; attached account `01B369-33874E-C921A9`, `My Billing Account`, open |
| Trial and budget | Owner confirms active trial and $5/month project budget with 50%, 90%, 100% actual-spend alerts |
| Raw absence | `datasets.list` contains only `ga4_analytics`; `datasets.get` for `ga4_raw` returns NotFound |
| Analytics readiness | US; both expiration defaults null; all seven existing relation expirations null |
| Exact source | `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_20201101`, US |
| Source metadata | 31,272 rows; 23,566,064 logical bytes; 23 top-level / 108 total schema fields |
| October project query inventory | 72 queries; 36,161,191,936 billed bytes; no missing query totals; SCRIPT parents excluded |
| Local fixtures | 12 extractor/reconciliation tests pass, zero failures |

The source row/byte counts above are metadata, not an executed source aggregate.
The inventory uses `jobs.list` metadata, not a billable SQL query. It amounts to
3.288841% of 1 TiB, but does not establish billing-account-wide remaining free
allowance or total Cloud Billing spend. Trial/budget details are owner-confirmed;
no Budget API was enabled or successfully queried in this scope. Budget alerts
do not impose a spending cap. Initial gcloud sandbox attempts failed on its local
credential cache; the same read-only checks succeeded with filesystem approval.
An initial stdin helper failed during dotenv discovery before cloud access;
its corrected metadata-only invocation succeeded. After owner go, the immediate
pre-write checks reconfirmed ACTIVE/enabled state, raw absence, matching source
schema/count/byte metadata, unchanged analytics and unchanged Power BI files.
An ADC-based project lookup returned 403; read-only gcloud fallback succeeded
with credential-cache filesystem approval. No API was enabled.

The native dry-run command succeeded with **23,566,064 bytes**:

```bash
PYTHONMALLOC=malloc PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked dotenv run -- python -m pipeline.extract_day \
  2020-11-01 --run-label owner_20201101 --max-bytes-billed 33554432 --dry-run
```

Its SQL names just this physical source shard:

```sql
SELECT PARSE_DATE('%Y%m%d', event_date) AS event_date, * EXCEPT(event_date)
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_20201101`
```

The dry run itself is free. At the current US on-demand rate of $6.25/TiB,
rounding the scan to 23 MiB (24,117,248 bytes) gives **$0.0001370906829833984375**
for the load query before free allowance or credits. The 32 MiB cap limits each
proposed query to **$0.00019073486328125**. The load plus two verification SELECTs
would therefore be capped at **$0.00057220458984375** in gross query cost.
[Google query pricing](https://cloud.google.com/bigquery/pricing),
[dry-run behavior](https://docs.cloud.google.com/bigquery/docs/running-queries).

For storage planning only, a conservative 32 MiB raw copy at $0.023/GiB-month
is approximately **$0.00071875/month** before free storage allowance. Actual raw
bytes will be read back after loading; this bound is not a measured raw size.
The existing source is about 22.47 MiB, and converting its date string to DATE
preserves all other fields. The proposed operation stays comfortably within the
$5 budget on an incremental basis: the gross query caps plus a full month of
this storage estimate total less than $0.002. Existing project-wide spend remains
unverified. The free tier currently includes 1 TiB of analysis and 10 GiB of
storage per month; account-wide availability is not assumed in these estimates.
[Google storage and free-tier pricing](https://cloud.google.com/bigquery/pricing).

## Exact approved and completed resource/load command

This command is retained as execution evidence. The partition is now populated;
no second load/rerun was performed or included in this scope.

```bash
PYTHONMALLOC=malloc PYTHONPATH=src UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python \
  uv run --locked dotenv run -- python -m pipeline.extract_day \
  2020-11-01 --run-label owner_20201101 --max-bytes-billed 33554432
```

Scope: create only US dataset `ga4-checkout-funnel.ga4_raw` if absent and table
`ga4-checkout-funnel.ga4_raw.ga4_events` if absent. Its source-derived schema has
23 top-level / 108 total fields; only `event_date` changes from STRING to DATE.
All other names, types, modes and nested shapes are preserved. Partition daily
on `event_date`, cluster on `event_name`, and retain no dataset default, table
or partition expiration. The extractor rejects incompatible existing metadata.

Write **only `ga4-checkout-funnel.ga4_raw.ga4_events$20201101`**, using
`WRITE_TRUNCATE`, query `CREATE_NEVER`, cache disabled and the 33,554,432-byte cap.
This is a query into a destination partition and is estimated as a query;
free batch-ingestion pricing is not substituted for its scan cost.

The destination was rechecked absent before writes. Native verification used
metadata APIs for actual row/byte counts, schema, expiration settings,
partitioning, clustering and job processed/billed bytes. It executed only these
two read-only SELECTs, each dry-run first and capped at 33,554,432 bytes:

1. `ga4_raw.INFORMATION_SCHEMA.PARTITIONS`, filtered to `table_name = 'ga4_events'`,
   to verify the only populated partition is `20201101` and inspect its row/byte
   metadata. No other source date is read.
2. The existing `pipeline.reconcile.reconciliation_sql` for `2020-11-01`, comparing
   this source shard with raw `event_date = DATE '2020-11-01'`. All eight declared
   count/transaction/purchase-revenue signals must match exactly, including null
   totals. This is only the first-day extraction verification, not completion
   of the broader P5.4 item.

Executed job IDs, real processed/billed bytes, partition metadata, schema checks
and actual comparison output are saved and read back before marking P5.2
complete. Twelve local extractor/reconciliation fixtures pass. The ignored
typed verification helper passes Ruff and saves job IDs before fetching results
so a local retry resumes the same read job. Local fixtures verify partition
targeting and `WRITE_TRUNCATE`; this single native load does not establish an
executed rerun. No automatic second load is included.

Stopped at P5.2. No other date, marts, replay, Airflow, backfill, cost comparison,
service accounts, GitHub cloud workflow, push or tag is included. Existing
`powerbi/` file hashes, Git status and index entries were checked unchanged;
the offline report and all canonical metrics remain preserved.
