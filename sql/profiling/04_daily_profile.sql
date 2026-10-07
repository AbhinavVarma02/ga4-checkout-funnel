-- The session key follows the brief; validate null rates before accepting totals.
WITH events AS (
    SELECT
        event_date,
        event_name,
        user_pseudo_id,
        (
            SELECT ANY_VALUE(param.value.int_value)
            FROM UNNEST(event_params) AS param
            WHERE param.key = 'ga_session_id'
        ) AS ga_session_id
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE _table_suffix BETWEEN '20201101' AND '20210131'
)

SELECT
    event_date,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_pseudo_id) AS user_count,
    COUNT(DISTINCT IF(
        user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL,
        CONCAT(user_pseudo_id, '.', CAST(ga_session_id AS STRING)),
        NULL
    )) AS observed_session_count,
    COUNTIF(user_pseudo_id IS NULL) AS null_user_id_events,
    COUNTIF(ga_session_id IS NULL) AS null_session_id_events,
    COUNTIF(event_name = 'first_visit') AS first_visit_events,
    COUNTIF(event_name = 'purchase') AS purchase_events
FROM events
GROUP BY event_date
ORDER BY event_date;
