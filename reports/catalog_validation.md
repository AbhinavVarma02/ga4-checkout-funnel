# Full actual dbt catalog verification

Human Step #9 / P2.4–P2.6 is complete. The real full command succeeded:

```bash
UV_CACHE_DIR=.uv-cache UV_PYTHON_INSTALL_DIR=.uv-python uv run --locked dotenv run -- dbt docs generate --project-dir dbt --profiles-dir dbt
```

The actual `../dbt/target/catalog.json` (local generated artifact),
`../dbt/target/manifest.json` (local generated artifact) and
`../dbt/target/index.html` (local generated artifact) are generated locally and ignored by Git.
Their exact hashes, native invocation, actual catalog contents, source metadata,
job IDs and byte evidence are saved under `warehouse_builds.p2_6_catalog` in
[metrics.json](metrics.json). No empty-catalog artifact is substituted for this
result. The catalog has no generation errors.

All seven model relations and all 118 model columns match actual BigQuery
metadata by relation identity/type, column names, order and types. Every model
and declared column has a nonempty description in the same invocation's dbt
manifest. Documentation combines these descriptions with actual catalog types;
warehouse comments were not altered or claimed to be persisted.

| Model | Actual, described columns |
|---|---:|
| stg_ga4_events | 17 |
| stg_ga4_items | 17 |
| int_sessions | 27 |
| fct_sessions | 28 |
| fct_funnel_daily | 12 |
| fct_product_daily | 12 |
| dim_date | 5 |

The public `events_*` source now also has actual catalog metadata: 108 flattened
fields, matching a metadata-API read of `events_20210131`, and 92 shards spanning
20201101–20210131. The raw source remains declared in the manifest but intentionally
uncreated and absent from the actual warehouse catalog. Creating it would exceed
this approval and is not needed to document the approved sandbox models.

Initial native generation included all models but omitted the public wildcard.
The pinned adapter filters the date-shard prefix before restoring `*` in the
output. A narrow [catalog macro](../dbt/macros/catalog.sql) normalizes only this
approved public wildcard for that filter, then delegates to the native adapter
through its `dbt` namespace. The first namespace attempt failed compilation and
produced no catalog metadata query jobs; it was corrected before the successful
generation. No business model SQL or persistent warehouse metadata changed.

The initial two native metadata SELECTs passed dry runs at 41,943,040 bytes each.
The refreshed preflight process later exited with native status 134 during
compilation (`stack smashing detected`), before capturing the revised metadata
queries; its cause is unconfirmed. The final native docs command succeeded.
Exact final metadata SQL was subsequently dry-run at the same estimates; these
are explicitly labeled post-run confirmations, not pre-execution checks.
Both final jobs retained the 21,474,836,480-byte per-query cap and processed
83,886,080 bytes in total, reporting 104,857,600 billed bytes. Including the
initial actual catalog attempt, four metadata jobs processed 167,772,160 bytes
and report 209,715,200 billed bytes. Byte statistics are not dollar-charge claims.

The optional `table_owner` agate warning appeared again; the native command
succeeded, actual catalog errors are null and schema verification passes.
Complete metadata inventory confirms all seven persistent relations, dataset
inventory and expiration settings remain unchanged. Billing was rechecked
disabled after execution. No raw/replay resource, extraction, Phase 5 load,
backfill, billing change, owner-file deletion, remote push or release occurred.

All 92 Python tests, Python lint/format, standalone and fixture SQL lint, and
real offline dbt SQL lint pass. Historical metric sections, earlier build evidence,
BI export provenance and prototype inputs are unchanged. This closes P2.6 and
Human Step #9 only; the other owner gates and full project definition of done
remain pending.
