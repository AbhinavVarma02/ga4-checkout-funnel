# P5.7 / Gate #24: native partition comparison complete

Status: **COMPLETE.** The owner approved the [exact Gate #24 command](partition_comparison_validation.md).
Execution at `c2e11cb2c06527c7663b657f1ee1b802b899a20f` completed two fresh
no-charge dry runs and exactly two uncached US SELECTs, each capped at
**134,217,728 bytes / 128 MiB**. The CLI exited 0 and its durable attempt receipt
is `passed`. No query was retried or rerun.

Sources: `partition_comparison` and `warehouse_builds.p5_7_partition_comparison`
in [metrics.json](metrics.json), plus the preserved
[execution receipt](partition_comparison_attempt.json). The original preparation
remains under `continuation_validation.p5_7_gate24_preparation`.

## Same seven-day results; different scan scope

Both queries read only `ga4-checkout-funnel.ga4_raw.ga4_events`. Their SQL and
DATE parameters are identical except for the filtered query's
`WHERE event_date BETWEEN @first_day AND @last_day`, January 25–31, 2021.
The selected columns are event date, event name and USD purchase revenue.

| Actual result | Unfiltered control | Filtered |
|---|---:|---:|
| Rows in scan scope | 4,295,584 | 273,507 |
| January 25–31 events | 273,507 | 273,507 |
| Observed window dates | 7 | 7 |
| Window purchase events | 343 | 343 |
| Window USD purchase-event revenue | 5,546 | 5,546 |

Seven existing public-source daily profiling rows independently match the
window's event/purchase counts. The unfiltered scan-scope row count also matches
the existing full-window source event total. Those checks reuse saved results;
no source or reconciliation SELECT was repeated. Revenue equality is verified
between the two real comparison queries, without an additional revenue query.
NULL purchase revenue contributes zero identically in both alternatives; this
comparison does not replace the pipeline's explicit null-versus-zero gate.

## Actual query bytes

| Alternative | Fresh dry-run estimate | Actual processed bytes | Actual billed bytes |
|---|---:|---:|---:|
| Unfiltered | 90,364,769 | 90,364,769 | 91,226,112 |
| Filtered | 5,685,678 | 5,685,678 | 10,485,760 |
| Sum | 96,050,447 | 96,050,447 | 101,711,872 |

The filtered query processes **84,679,091 fewer bytes / 93.708081% less** and
is billed **80,740,352 fewer bytes / 88.505747% less** than this control.
The billed reduction differs from the processed reduction because the control
rounds to **87 MiB**, while the filtered query reaches the **10 MiB minimum**.
This is a measured query-byte comparison over this table/window/SQL; it does not
measure a seven-day pipeline cost, an invoice or realized dollar savings.

| Alternative | Actual query ID | Native execution, UTC |
|---|---|---|
| Unfiltered | `p5_7_unfiltered_e2f92263c00e4447947c4439d9283ee0` | 2026-10-06 22:57:05.168–22:57:05.581 |
| Filtered | `p5_7_filtered_68077d30a2d444ee93eea1408c380dae` | 2026-10-06 22:57:06.289–22:57:06.534 |

Independent existing-job/result APIs verify both jobs are `DONE`, error-free,
uncached SELECTs with the exact SQL/hashes, DATE parameters, labels, project,
US location, raw-only referenced table, reviewed cap, per-job bytes and saved
aggregate rows. A bounded job-list API lookup finds exactly these two IDs under
`ga4_run=p5_7_gate24_20210125`; no additional execution is present in that scope.
Verification submits **zero SQL queries**. Native configuration, job references,
results and byte/time attributes are retained in the completion evidence.

The preparation's **30 focused tests**, changed Python lint/format, both SQLFluff
parses, CLI help and pinned native SDK checks remain valid: code and dependencies
are unchanged. No full suite was rerun. A local evidence builder initially
expected statistics in `QueryJob.to_api_repr()`; this SDK returns configuration
and job reference. The evidence record was corrected to use the independently
verified explicit byte/time/result attributes, without repeating either query.

## Additive accounting and preservation

The experiment bills **101,711,872 bytes / 97 MiB / 0.0947265625 GiB** total.
At the saved **$6.25/TiB** reference rate, gross query arithmetic is
**$0.0005781650543212890625**, before unverified allowance/credits. The rate/source
and limitations remain in the preparation evidence. Account-wide usage, credits,
storage/other charges and an invoice were not inspected or inferred.

| Recorded scope | Billed bytes | Billed GiB | Submitted records |
|---|---:|---:|---:|
| Original completed P5.6 window, unchanged | 381,591,486,464 | 355.384765625 | 3,337 |
| These two Gate #24 queries only | 101,711,872 | 0.0947265625 | 2 |
| Combined recorded scopes | 381,693,198,336 | 355.4794921875 | 3,339 |

The original **512 GiB** boundary is unchanged. Combined-scope headroom is
**168,062,615,552 bytes / 156.5205078125 GiB**. These are explicitly additive
recorded scopes, not a new account-wide total. Original P5.6 metric values and
its 3,337-record cumulative cache remain intact, with its leaf and SCRIPT
accounting still agreeing. The cache was neither extended nor reset; the two
new IDs and actual bytes are retained separately.

All prior metric values are preserved. Only the two comparison dry-run entries
are normally refreshed to the approved 128 MiB execution cap/status/IDs; their
original plans remain preserved in preparation evidence. All other dry-run
values, **95 CSV rows**, **44 saved Gate #23 artifact hashes**, task sources,
configs, canonical exports and **300 owner Power BI files with index/status**
remain unchanged. Existing backfill 4, all completed history and the Gate #23
paused/idle/exited-guard checkpoint were not activated or modified.

No warehouse write, raw load, dbt build, Airflow action, deletion, IAM/workflow,
next checklist item, push or tag occurred. **P5.7 and Needs from human #24 are
complete.** The approval permits no repeat or additional query. P5.9's
service-account/manual workflow and final acceptance/release remain separate.
