-- Full window; dry-run before execution and record estimated bytes.
SELECT
    event_name,
    COUNT(*) AS event_count,
    COUNT(DISTINCT event_date) AS active_dates
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _table_suffix BETWEEN '20201101' AND '20210131'
GROUP BY event_name
ORDER BY event_count DESC, event_name ASC;
