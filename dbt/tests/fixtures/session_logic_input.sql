-- Fixture synthetic events only; never public GA4 rows.
SELECT
    user_pseudo_id,
    ga_session_id,
    event_date,
    event_timestamp_micros,
    event_name,
    'United States' AS country,
    'fixture_source' AS first_touch_source,
    'fixture_medium' AS first_touch_medium,
    purchase_revenue_usd,
    IF(user_pseudo_id = 'fixture_user_1', 'mobile', 'desktop') AS device_category
FROM UNNEST([
    STRUCT(
        'fixture_user_1' AS user_pseudo_id, 1 AS ga_session_id,
        DATE '2020-11-01' AS event_date, 0 AS event_timestamp_micros,
        'first_visit' AS event_name, CAST(NULL AS NUMERIC) AS purchase_revenue_usd
    ),
    STRUCT('fixture_user_1', 1, DATE '2020-11-01', 1, 'session_start', CAST(NULL AS NUMERIC)),
    STRUCT('fixture_user_1', 1, DATE '2020-11-01', 2, 'add_to_cart', CAST(NULL AS NUMERIC)),
    STRUCT('fixture_user_1', 1, DATE '2020-11-01', 3, 'view_item', CAST(NULL AS NUMERIC)),
    STRUCT('fixture_user_1', 1, DATE '2020-11-01', 4, 'add_to_cart', CAST(NULL AS NUMERIC)),
    STRUCT('fixture_user_1', 1, DATE '2020-11-01', 5, 'begin_checkout', CAST(NULL AS NUMERIC)),
    STRUCT('fixture_user_1', 1, DATE '2020-11-02', 6, 'purchase', NUMERIC '10'),
    STRUCT('fixture_user_2', 2, DATE '2020-11-01', 7, 'purchase', NUMERIC '5')
])
