-- BigQuery metadata only: inspect every daily table before choosing model fields.
SELECT
    table_name,
    column_name,
    data_type
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name BETWEEN 'events_20201101' AND 'events_20210131'
ORDER BY table_name, ordinal_position;
