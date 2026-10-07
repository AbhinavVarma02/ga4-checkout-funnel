-- Inspect nested commerce, item, attribution, and event parameter fields.
SELECT
    table_name,
    field_path,
    data_type
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE
    table_name BETWEEN 'events_20201101' AND 'events_20210131'
    AND (
        field_path LIKE 'ecommerce.%'
        OR field_path LIKE 'items.%'
        OR field_path LIKE 'traffic_source.%'
        OR field_path LIKE 'event_params.%'
    )
ORDER BY table_name, field_path;
