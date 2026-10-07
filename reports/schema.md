# Observed GA4 public-export schema

This report uses actual queries against `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` for 2020-11-01 through 2021-01-31, submitted from the billing-disabled `ga4-checkout-funnel` project. Every count below comes from [metrics.json](metrics.json) under `profiling`; estimated bytes for every query are in [dry_runs.json](dry_runs.json). These are public-export counts, not GA4 interface totals. Queries were dry-run before execution.

## Columns and nested fields

`event_date` is `STRING`; `event_timestamp` is `INT64`; `event_name` and `user_pseudo_id` are `STRING`. `event_params` and `items` are arrays of structs. `device.category` and `geo.country` are present. The nested-schema result contains these revenue and transaction fields: `ecommerce.purchase_revenue`, `ecommerce.purchase_revenue_in_usd`, `ecommerce.transaction_id`, `items.item_revenue`, `items.item_revenue_in_usd`, and top-level `event_value_in_usd`. The revenue fields are `FLOAT64`; the transaction ID is `STRING`. `traffic_source.source`, `.medium`, and `.name` are also present, but describe first-touch acquisition. Source: `profiling.01_schema_columns.rows` and `profiling.01_schema_nested.rows`.

The `items` struct also contains `item_id`, `item_name`, `item_brand`, `item_variant`, `item_category` through `item_category5`, `price`, `price_in_usd`, `quantity`, coupon, affiliation, location, list, promotion, creative, and refund fields. `item_id`, `item_name`, and `item_category` are present on all observed item rows; `item_revenue` appears only on purchase item rows and is missing on some of those. Source: `profiling.01_schema_nested.rows` and `profiling.08_items_profile.rows`.

## Observed event names

Counts and active-date counts are from `profiling.02_event_names.rows`.

| Event | Events | Active dates |
|---|---:|---:|
| page_view | 1,350,428 | 92 |
| user_engagement | 1,058,721 | 92 |
| scroll | 493,072 | 92 |
| view_item | 386,068 | 92 |
| session_start | 354,970 | 92 |
| first_visit | 257,462 | 92 |
| view_promotion | 190,104 | 92 |
| add_to_cart | 58,543 | 74 |
| begin_checkout | 38,757 | 92 |
| select_item | 31,007 | 70 |
| view_search_results | 26,172 | 92 |
| add_shipping_info | 19,722 | 92 |
| add_payment_info | 13,899 | 92 |
| select_promotion | 9,450 | 92 |
| purchase | 5,692 | 92 |
| click | 1,446 | 92 |
| view_item_list | 71 | 33 |

`session_start`, `view_item`, `add_to_cart`, `begin_checkout`, and `purchase` therefore exist. `add_to_cart` is absent on some dates; the ordered and any-order funnels must not assume every session recorded every step.

## Observed event parameter keys

Occurrences are from `profiling.03_event_params.rows`; a parameter can appear on many events in the same session.

| Key | Occurrences | Key | Occurrences |
|---|---:|---|---:|
| ga_session_id | 4,295,584 | ga_session_number | 4,295,584 |
| page_location | 4,295,584 | page_title | 4,276,104 |
| engaged_session_event | 4,116,237 | session_engaged | 3,996,312 |
| debug_mode | 3,682,991 | page_referrer | 3,206,512 |
| all_data | 2,828,174 | clean_event | 2,828,040 |
| engagement_time_msec | 2,431,818 | medium | 1,439,214 |
| campaign | 1,439,167 | source | 1,428,080 |
| percent_scrolled | 493,072 | term | 338,704 |
| entrances | 332,179 | gclid | 118,481 |
| gclsrc | 116,846 | currency | 39,313 |
| search_term | 26,172 | unique_search_term | 20,967 |
| dclid | 15,701 | payment_type | 5,242 |
| tax | 5,242 | transaction_id | 5,242 |
| value | 5,242 | shipping_tier | 4,159 |
| coupon | 3,075 | promotion_name | 2,270 |
| link_domain | 1,446 | link_url | 1,446 |
| outbound | 1,446 | link_classes | 6 |

`ga_session_id` is an integer parameter on its observed occurrences (`profiling.03_event_params.rows`, `ga_session_id.int_values`). `source` and `medium` occur as string parameters, but existence alone does not make them session-level attribution.

## Attribution check

Among sessions with non-null `user_pseudo_id` and `ga_session_id`, event-param `source` and `medium` both occur in 264,810 sessions. Neither appears on any observed `session_start` event. Within-session values vary: 63,540 sessions have multiple source values and 53,993 have multiple medium values. In 95,318 sessions, no event-param source occurs although a first-touch source is present. Source: `profiling.09_session_attribution.rows[0]`. These are event-level, inconsistently populated values, not a defensible stable session-level pair. Use `traffic_source.source` and `.medium` as **first-touch** channel, labeled that way in every output; do not present them as the session's acquisition source.

## Item-array evidence

Observed item rows by event are in `profiling.08_items_profile.rows`: `view_item` 2,748,246; `add_to_cart` 667,426; `select_item` 329,364; `view_promotion` 134,602; `begin_checkout` 77,980; `purchase` 16,003; `select_promotion` 8,595; and `view_item_list` 516. On purchase item rows, 448 have null `item_revenue`; the non-null `item_revenue` sum is 362,110.0. The event-level purchase revenue and its gap against this item sum still require profiling. These are item rows, not distinct events, sessions, or products.

## Query costs and caveats

The largest P1.2 dry-run estimate was 1,604,978,110 bytes for `09_session_attribution` (`dry_runs.json`, `09_session_attribution.estimated_bytes`); the profiling runner capped execution at 20 GiB per query. This estimate is bytes processed, not bytes billed or a currency cost. The public data is obfuscated, and no comparison with the GA4 UI is implied.
