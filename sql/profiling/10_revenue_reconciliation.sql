-- Compare purchase-event revenue with purchase-item revenue in USD.
WITH purchases AS (
    SELECT
        ecommerce.purchase_revenue,
        ecommerce.purchase_revenue_in_usd,
        event_value_in_usd,
        ARRAY_LENGTH(items) AS item_rows,
        (
            SELECT SUM(CAST(item.item_revenue_in_usd AS BIGNUMERIC))
            FROM UNNEST(items) AS item
        ) AS item_revenue_in_usd,
        (
            SELECT COUNTIF(item.item_revenue_in_usd IS NULL)
            FROM UNNEST(items) AS item
        ) AS null_item_revenue_rows
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE
        _table_suffix BETWEEN '20201101' AND '20210131'
        AND event_name = 'purchase'
)

SELECT
    COUNT(*) AS purchase_events,
    COUNTIF(purchase_revenue IS NULL) AS null_purchase_revenue_events,
    COUNTIF(purchase_revenue_in_usd IS NULL) AS null_purchase_revenue_usd_events,
    COUNTIF(event_value_in_usd IS NULL) AS null_event_value_usd_events,
    COUNTIF(item_revenue_in_usd IS NULL) AS null_item_revenue_sum_events,
    SUM(item_rows) AS purchase_item_rows,
    SUM(null_item_revenue_rows) AS null_item_revenue_rows,
    SUM(CAST(purchase_revenue AS BIGNUMERIC)) AS purchase_revenue,
    SUM(CAST(purchase_revenue_in_usd AS BIGNUMERIC)) AS purchase_revenue_in_usd,
    SUM(CAST(event_value_in_usd AS BIGNUMERIC)) AS event_value_in_usd,
    SUM(COALESCE(item_revenue_in_usd, 0)) AS item_revenue_in_usd,
    SUM(CAST(purchase_revenue_in_usd AS BIGNUMERIC))
    - SUM(COALESCE(item_revenue_in_usd, 0)) AS event_minus_item_revenue_usd,
    COUNTIF(
        CAST(purchase_revenue_in_usd AS BIGNUMERIC)
        != COALESCE(item_revenue_in_usd, 0)
    ) AS purchase_events_with_revenue_gap
FROM purchases;
