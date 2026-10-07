-- Observed commerce events and nested fields, grouped by export date and event.
SELECT
    event_date,
    event_name,
    COUNT(*) AS event_count,
    COUNTIF(ecommerce.transaction_id IS NULL)
        AS null_transaction_id_events,
    COUNTIF(ecommerce.purchase_revenue IS NULL)
        AS null_purchase_revenue_events,
    COUNTIF(ecommerce.purchase_revenue_in_usd IS NULL)
        AS null_purchase_revenue_usd_events,
    SUM(ecommerce.purchase_revenue)
        AS purchase_revenue_sum,
    SUM(ecommerce.purchase_revenue_in_usd)
        AS purchase_revenue_usd_sum,
    SUM(ARRAY_LENGTH(items)) AS item_rows
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    _table_suffix BETWEEN '20201101' AND '20210131'
    AND event_name IN (
        'view_item', 'add_to_cart', 'begin_checkout',
        'add_shipping_info', 'add_payment_info', 'purchase'
    )
GROUP BY event_date, event_name
ORDER BY event_date, event_name;
