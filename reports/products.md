# Product and category performance

Real read-only public-export results for 2020-11-01 through 2021-01-31. Both queries reconcile item USD revenue and missing-revenue rows to the independent source profile. No warehouse relation was created.

Reach means a view and purchase anywhere in the same two-field session key, in any order. Category reach can involve different products in that category. Each category deduplicates sessions directly; product session counts are not summed. Sessions can appear in multiple categories.

## Categories ranked by observed item revenue

| Category | Viewing sessions | Purchase sessions | Both | Purchase without view | Item USD revenue | Both / views |
|---|---:|---:|---:|---:|---:|---|
| Apparel | 3191 | 2627 | 272 | 2355 | 171727.00 | 272/3191 |
| New | 1499 | 942 | 82 | 860 | 25813.00 | 82/1499 |
| Bags | 2688 | 513 | 190 | 323 | 23860.00 | 190/2688 |
| Campus Collection | 1529 | 761 | 236 | 525 | 20061.00 | 236/1529 |
| Accessories | 35 | 794 | 0 | 794 | 17815.00 | 0/35 |
| Uncategorized Items | 0 | 441 | 0 | 441 | 17394.00 | undefined |
| Shop by Brand | 436 | 662 | 15 | 647 | 16960.00 | 15/436 |
| Drinkware | 3361 | 550 | 327 | 223 | 15807.00 | 327/3361 |
| Lifestyle | 2005 | 460 | 49 | 411 | 13423.00 | 49/2005 |
| Clearance | 0 | 499 | 0 | 499 | 11476.00 | undefined |

Source: `reports/metrics.json`, `product_analysis.categories` (first ten rows; ordered by revenue).

## Products ranked by observed item revenue

| Product | Item ID | Category | Item USD revenue | Views | Purchase without view |
|---|---|---|---:|---:|---:|
| Google Canteen Bottle Black | 9195292 | Drinkware | 5303.00 | 0 | 118 |
| Google Utility BackPack | 9195140 | Bags | 5256.00 | 0 | 40 |
| Google Zip Hoodie F/C | 9195130 | Apparel | 4632.00 | 0 | 82 |
| Google Campus Bike | 9194259 | Accessories | 4352.00 | 0 | 99 |
| Google Incognito Techpack V2 | 9197759 | Bags | 4053.00 | 0 | 27 |

Source: `reports/metrics.json`, `product_analysis.products` (first five rows).

Across 4761 item/category groups, 0 groups have a matched view and purchase. This is an observed matching limitation, not evidence that product pages never convert. Missing views, different item/category keys, or obfuscation can break matching; these aggregates do not identify the cause. Do not use this product conversion to rank product-page fixes.

Apparel leads observed item revenue in this export. Treat category reach as descriptive rather than causal: broad categories, unmatched purchases, and inconsistent labels limit comparison. Keep original category labels; no unverified taxonomy mapping was applied.

Item revenue is a product diagnostic, not canonical project revenue. Canonical revenue remains purchase-event USD revenue; the source reconciliation gap stays visible under `profiling_summary.event_minus_item_revenue_usd`.

LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users
LIMIT: obfuscated sample data; some totals don't fully reconcile
LIMIT: channel results are first-touch unless session-level source exists in the data
LIMIT: the daily pipeline replays historical daily tables as a simulated feed
