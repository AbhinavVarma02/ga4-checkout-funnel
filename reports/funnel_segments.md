# Measured funnel by device and country

The compiled session model was aggregated read-only by earliest-event device category and country. The 317 device-country rows in `reports/metrics.json`, `readonly_funnel_segments.rows`, reconcile to the global session counts and revenue before publication. `analysis.by_device` and `analysis.by_country` are exact rollups of those rows, sorted by all-session count. Funnel step counts below are cumulative **any-order distinct sessions**; strict ordered counts and exact step-conversion fractions are also stored beside each segment in `global_funnel`.

| Device | All sessions | Purchase sessions | Reached view_item | Reached add_to_cart | Reached begin_checkout | Reached purchase | Purchase-event USD revenue | `reports/metrics.json` key |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| desktop | 208,942 | 2,749 | 43,813 | 8,619 | 3,377 | 1,592 | 208,815 | `analysis.by_device[0]` |
| mobile | 143,185 | 1,995 | 29,799 | 5,962 | 2,362 | 1,162 | 146,768 | `analysis.by_device[1]` |
| tablet | 8,002 | 104 | 1,659 | 316 | 129 | 62 | 6,582 | `analysis.by_device[2]` |

The largest modeled opportunity in each device segment is `session_start → view_item`, but that ranking uses an **assumption** about how recovered dropouts would behave (`analysis.by_device[*].dropoff_opportunities[0]`). Desktop has more such lost sessions in absolute terms than mobile; this is a prioritization clue, not proof of the cause or a causal treatment effect.

The leading countries by all-session count are shown below. The complete country rollup, including exact conversion fractions, strict reach, revenue, and modeled transition opportunities, is in `analysis.by_country`.

| Country | All sessions | Purchase sessions | Reached view_item | Reached add_to_cart | Reached begin_checkout | Reached purchase | `reports/metrics.json` key |
|---|---:|---:|---:|---:|---:|---:|---|
| United States | 158,155 | 2,117 | 33,110 | 6,615 | 2,630 | 1,254 | `analysis.by_country[0]` |
| India | 33,769 | 449 | 7,076 | 1,355 | 509 | 255 | `analysis.by_country[1]` |
| Canada | 26,824 | 390 | 5,733 | 1,163 | 482 | 229 | `analysis.by_country[2]` |
| United Kingdom | 11,327 | 151 | 2,351 | 462 | 182 | 91 | `analysis.by_country[3]` |
| France | 7,162 | 102 | 1,461 | 289 | 109 | 60 | `analysis.by_country[4]` |

Country and device are attached from each session's earliest observed event; they are not independently reattributed at each funnel step. No real company, experiment, or GA4 interface result is represented here.
