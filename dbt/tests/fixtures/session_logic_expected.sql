-- Fixture expected session results only; never public GA4 rows.
SELECT
    'fixture_user_1' AS user_pseudo_id,
    1 AS ga_session_id,
    DATE '2020-11-01' AS session_start_date,
    7 AS event_count,
    TRUE AS is_new_user_in_window,
    TRUE AS has_purchase,
    TRUE AS ordered_purchase,
    NUMERIC '10' AS purchase_revenue_usd

UNION ALL

SELECT
    'fixture_user_2' AS user_pseudo_id,
    2 AS ga_session_id,
    DATE '2020-11-01' AS session_start_date,
    1 AS event_count,
    FALSE AS is_new_user_in_window,
    TRUE AS has_purchase,
    FALSE AS ordered_purchase,
    NUMERIC '5' AS purchase_revenue_usd
