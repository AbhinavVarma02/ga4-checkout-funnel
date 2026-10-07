-- Bounded first-day replay validation; no public-source read or warehouse write.
WITH raw_events AS (
    SELECT
        user_pseudo_id,
        event_name,
        (
            SELECT ANY_VALUE(param.value.int_value)
            FROM UNNEST(event_params) AS param
            WHERE param.key = 'ga_session_id'
        ) AS ga_session_id,
        SAFE_CAST(ecommerce.purchase_revenue_in_usd AS NUMERIC) AS revenue
    FROM `ga4-checkout-funnel.ga4_raw.ga4_events`
    WHERE event_date = DATE '2020-11-01'
),

valid_events AS (
    SELECT * FROM raw_events
    WHERE user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL
),

source_summary AS (
    SELECT
        (SELECT COUNT(*) FROM raw_events) AS raw_rows,
        COUNT(DISTINCT TO_JSON_STRING(STRUCT(user_pseudo_id, ga_session_id)))
            AS valid_sessions,
        COUNTIF(event_name = 'purchase') AS keyed_purchase_events,
        COUNTIF(event_name = 'purchase' AND revenue IS NULL)
            AS keyed_missing_revenue_events,
        COALESCE(SUM(IF(event_name = 'purchase', COALESCE(revenue, 0), 0)), 0)
            AS keyed_purchase_revenue_usd
    FROM valid_events
),

session_summary AS (
    SELECT
        COUNT(*) AS sessions,
        COALESCE(SUM(purchase_events), 0) AS purchase_events,
        COALESCE(SUM(purchase_events_missing_revenue), 0) AS missing_revenue_events,
        COALESCE(SUM(purchase_revenue_usd), 0) AS purchase_revenue_usd
    FROM `ga4-checkout-funnel.ga4_replay_analytics.fct_sessions`
),

relation_rows AS (
    SELECT
        'fct_sessions' AS relation_name,
        session_start_date AS row_date,
        TO_HEX(SHA256(TO_JSON_STRING(session_row))) AS row_hash
    FROM `ga4-checkout-funnel.ga4_replay_analytics.fct_sessions` AS session_row
    UNION ALL
    SELECT
        'fct_funnel_daily' AS relation_name,
        session_start_date AS row_date,
        TO_HEX(SHA256(TO_JSON_STRING(funnel_row))) AS row_hash
    FROM `ga4-checkout-funnel.ga4_replay_analytics.fct_funnel_daily` AS funnel_row
    UNION ALL
    SELECT
        'fct_product_daily' AS relation_name,
        session_start_date AS row_date,
        TO_HEX(SHA256(TO_JSON_STRING(product_row))) AS row_hash
    FROM `ga4-checkout-funnel.ga4_replay_analytics.fct_product_daily` AS product_row
    UNION ALL
    SELECT
        'dim_date' AS relation_name,
        date_day AS row_date,
        TO_HEX(SHA256(TO_JSON_STRING(calendar_row))) AS row_hash
    FROM `ga4-checkout-funnel.ga4_replay_analytics.dim_date` AS calendar_row
),

relation_summary AS (
    SELECT
        relation_name,
        COUNT(*) AS row_count,
        COUNTIF(row_date IS NULL) AS null_date_rows,
        COUNT(DISTINCT row_date) AS distinct_dates,
        MIN(row_date) AS first_date,
        MAX(row_date) AS last_date,
        TO_HEX(SHA256(STRING_AGG(row_hash, '' ORDER BY row_hash))) AS fingerprint
    FROM relation_rows
    GROUP BY relation_name
)

SELECT TO_JSON_STRING(STRUCT(
    ARRAY(
        SELECT AS STRUCT * FROM relation_summary
        ORDER BY relation_name
    ) AS relations,
    (SELECT AS STRUCT * FROM source_summary) AS raw_source,
    (SELECT AS STRUCT * FROM session_summary) AS sessions
)) AS snapshot_json
