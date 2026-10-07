-- Verify whether event-level source and medium identify a stable session channel.
WITH event_values AS (
    SELECT
        event.user_pseudo_id,
        event.event_name,
        event.traffic_source.source AS first_touch_source,
        (
            SELECT ANY_VALUE(param.value.int_value)
            FROM UNNEST(event.event_params) AS param
            WHERE param.key = 'ga_session_id'
        ) AS ga_session_id,
        (
            SELECT ANY_VALUE(param.value.string_value)
            FROM UNNEST(event.event_params) AS param
            WHERE param.key = 'source'
        ) AS session_source,
        (
            SELECT ANY_VALUE(param.value.string_value)
            FROM UNNEST(event.event_params) AS param
            WHERE param.key = 'medium'
        ) AS session_medium
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS event
    WHERE _table_suffix BETWEEN '20201101' AND '20210131'
),

session_values AS (
    SELECT
        user_pseudo_id,
        ga_session_id,
        COUNT(DISTINCT session_source) AS distinct_sources,
        COUNT(DISTINCT session_medium) AS distinct_media,
        COUNTIF(session_source IS NOT NULL) AS source_events,
        COUNTIF(session_medium IS NOT NULL) AS medium_events,
        COUNTIF(first_touch_source IS NOT NULL) AS first_touch_events,
        COUNTIF(event_name = 'session_start' AND session_source IS NOT NULL)
            AS session_start_source_events,
        COUNTIF(event_name = 'session_start' AND session_medium IS NOT NULL)
            AS session_start_medium_events
    FROM event_values
    WHERE user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL
    GROUP BY user_pseudo_id, ga_session_id
)

SELECT
    COUNT(*) AS sessions_with_valid_key,
    COUNTIF(source_events > 0) AS sessions_with_source_param,
    COUNTIF(medium_events > 0) AS sessions_with_medium_param,
    COUNTIF(source_events > 0 AND medium_events > 0)
        AS sessions_with_source_and_medium_params,
    COUNTIF(distinct_sources > 1) AS sessions_with_multiple_source_values,
    COUNTIF(distinct_media > 1) AS sessions_with_multiple_medium_values,
    COUNTIF(session_start_source_events > 0) AS sessions_with_session_start_source,
    COUNTIF(session_start_medium_events > 0) AS sessions_with_session_start_medium,
    COUNTIF(source_events = 0 AND first_touch_events > 0)
        AS sessions_needing_first_touch_fallback
FROM session_values;
