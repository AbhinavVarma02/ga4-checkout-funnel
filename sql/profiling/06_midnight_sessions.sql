-- Count sessions whose observed events span daily export tables.
WITH events AS (
    SELECT
        user_pseudo_id,
        event_date,
        (
            SELECT ANY_VALUE(param.value.int_value)
            FROM UNNEST(event_params) AS param
            WHERE param.key = 'ga_session_id'
        ) AS ga_session_id
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE
        _table_suffix BETWEEN '20201101' AND '20210131'
        AND user_pseudo_id IS NOT NULL
),

sessions AS (
    SELECT
        user_pseudo_id,
        ga_session_id,
        MIN(event_date) AS first_event_date,
        MAX(event_date) AS last_event_date
    FROM events
    GROUP BY user_pseudo_id, ga_session_id
)

SELECT
    first_event_date AS session_start_date,
    COUNT(*) AS session_count,
    COUNTIF(first_event_date < last_event_date) AS crosses_midnight_count
FROM sessions
WHERE ga_session_id IS NOT NULL
GROUP BY session_start_date
ORDER BY session_start_date;
