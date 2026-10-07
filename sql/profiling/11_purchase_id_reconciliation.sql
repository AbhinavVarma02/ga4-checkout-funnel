-- Compare purchase events to distinct nonblank transaction IDs across all days.
WITH purchases AS (
    SELECT
        event_date,
        NULLIF(TRIM(ecommerce.transaction_id), '') AS transaction_id
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE
        _table_suffix BETWEEN '20201101' AND '20210131'
        AND event_name = 'purchase'
),

id_counts AS (
    SELECT
        transaction_id,
        COUNT(*) AS purchase_events,
        COUNT(DISTINCT event_date) AS active_dates
    FROM purchases
    WHERE transaction_id IS NOT NULL
    GROUP BY transaction_id
),

event_totals AS (
    SELECT
        COUNT(*) AS purchase_events,
        COUNTIF(transaction_id IS NULL) AS missing_or_blank_transaction_ids
    FROM purchases
),

id_totals AS (
    SELECT
        COUNT(*) AS distinct_nonblank_transaction_ids,
        COUNTIF(purchase_events > 1) AS repeated_transaction_ids,
        SUM(purchase_events - 1) AS extra_purchase_events_on_repeated_ids,
        COUNTIF(active_dates > 1) AS transaction_ids_across_dates
    FROM id_counts
)

SELECT * FROM event_totals CROSS JOIN id_totals;
