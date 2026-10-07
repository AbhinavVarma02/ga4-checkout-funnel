-- Compare purchase events with transaction ID coverage and uniqueness by day.
SELECT
    event_date,
    COUNT(*) AS purchase_events,
    COUNTIF(ecommerce.transaction_id IS NULL)
        AS null_transaction_id_events,
    COUNT(DISTINCT ecommerce.transaction_id)
        AS distinct_transaction_ids
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    _table_suffix BETWEEN '20201101' AND '20210131'
    AND event_name = 'purchase'
GROUP BY event_date
ORDER BY event_date;
