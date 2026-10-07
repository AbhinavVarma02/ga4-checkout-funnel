-- Inspect item array coverage and both item-level revenue fields by event.
SELECT
    event_name,
    COUNT(*) AS item_rows,
    COUNTIF(JSON_VALUE(TO_JSON_STRING(item), '$.item_id') IS NULL) AS null_item_id_rows,
    COUNTIF(JSON_VALUE(TO_JSON_STRING(item), '$.item_name') IS NULL) AS null_item_name_rows,
    COUNTIF(JSON_VALUE(TO_JSON_STRING(item), '$.item_category') IS NULL)
        AS null_item_category_rows,
    COUNTIF(JSON_VALUE(TO_JSON_STRING(item), '$.item_revenue') IS NULL)
        AS null_item_revenue_rows,
    COUNTIF(JSON_VALUE(TO_JSON_STRING(item), '$.item_revenue_in_usd') IS NULL)
        AS null_item_revenue_usd_rows,
    SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(item), '$.item_revenue') AS FLOAT64))
        AS item_revenue_sum,
    SUM(SAFE_CAST(JSON_VALUE(TO_JSON_STRING(item), '$.item_revenue_in_usd') AS FLOAT64))
        AS item_revenue_usd_sum
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS event
CROSS JOIN UNNEST(event.items) AS item
WHERE _table_suffix BETWEEN '20201101' AND '20210131'
GROUP BY event_name
ORDER BY item_rows DESC, event_name ASC;
