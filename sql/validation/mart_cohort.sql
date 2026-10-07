-- Independently regroup the public source, retaining sessionless first_visit.
WITH source_events AS (
    SELECT
        user_pseudo_id,
        event_name,
        CAST(ecommerce.purchase_revenue_in_usd AS NUMERIC) AS revenue_usd,
        PARSE_DATE('%Y%m%d', event_date) AS event_date,
        (
            SELECT MAX(param.value.int_value)
            FROM UNNEST(event_params) AS param
            WHERE param.key = 'ga_session_id'
        ) AS ga_session_id
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE _table_suffix BETWEEN '20201101' AND '20210131'
),

new_users AS (
    SELECT DISTINCT user_pseudo_id
    FROM source_events
    WHERE event_name = 'first_visit' AND user_pseudo_id IS NOT NULL
),

source_sessions AS (
    SELECT
        user_pseudo_id,
        ga_session_id,
        MIN(event_date) AS session_start_date,
        COUNT(*) AS event_count,
        COUNTIF(event_name = 'purchase') AS purchase_events,
        SUM(IF(event_name = 'purchase', COALESCE(revenue_usd, 0), 0)) AS revenue_usd
    FROM source_events
    WHERE user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL
    GROUP BY user_pseudo_id, ga_session_id
)

SELECT
    COUNTIF(source_session.user_pseudo_id IS NULL) AS extra_mart_sessions,
    COUNTIF(mart.user_pseudo_id IS NULL) AS missing_mart_sessions,
    COUNTIF(source_session.session_start_date IS DISTINCT FROM mart.session_start_date)
        AS start_date_mismatches,
    COUNTIF(source_session.event_count IS DISTINCT FROM mart.event_count) AS event_count_mismatches,
    COUNTIF(source_session.purchase_events IS DISTINCT FROM mart.purchase_events)
        AS purchase_count_mismatches,
    COUNTIF(source_session.revenue_usd IS DISTINCT FROM mart.purchase_revenue_usd)
        AS revenue_mismatches,
    COUNTIF(
        mart.user_cohort IS DISTINCT FROM IF(
            new_user.user_pseudo_id IS NOT NULL, 'new_in_window', 'no_observed_first_visit'
        )
    ) AS cohort_mismatches
FROM source_sessions AS source_session
FULL OUTER JOIN __fct_sessions__ AS mart
    ON
        source_session.user_pseudo_id = mart.user_pseudo_id
        AND source_session.ga_session_id = mart.ga_session_id
LEFT JOIN new_users AS new_user
    ON source_session.user_pseudo_id = new_user.user_pseudo_id;
