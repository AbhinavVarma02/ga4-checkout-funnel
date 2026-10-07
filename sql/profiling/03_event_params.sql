-- Confirm ga_session_id and whether source/medium are session-level parameters.
SELECT
    param.key AS param_key,
    COUNT(*) AS param_occurrences,
    COUNTIF(param.value.string_value IS NOT NULL) AS string_values,
    COUNTIF(param.value.int_value IS NOT NULL) AS int_values,
    COUNTIF(param.value.double_value IS NOT NULL) AS double_values,
    COUNTIF(param.value.float_value IS NOT NULL) AS float_values
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS event
CROSS JOIN UNNEST(event.event_params) AS param
WHERE _table_suffix BETWEEN '20201101' AND '20210131'
GROUP BY param_key
ORDER BY param_occurrences DESC, param_key ASC;
