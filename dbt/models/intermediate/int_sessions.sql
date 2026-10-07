-- One row per user_pseudo_id + ga_session_id, assigned to first export date.
WITH valid_events AS (
    SELECT *
    FROM {{ ref('stg_ga4_events') }}
    WHERE user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL
),

first_visit_users AS (
    SELECT DISTINCT user_pseudo_id
    FROM {{ ref('stg_ga4_events') }}
    WHERE event_name = 'first_visit' AND user_pseudo_id IS NOT NULL
),

grouped_sessions AS (
    SELECT
        user_pseudo_id,
        ga_session_id,
        MIN(event_date) AS session_start_date,
        MIN(event_timestamp_micros) AS first_event_timestamp_micros,
        ARRAY_AGG(
            STRUCT(device_category, country, first_touch_source, first_touch_medium)
            ORDER BY event_timestamp_micros, event_date, event_name LIMIT 1
        )[OFFSET(0)] AS first_event_dimensions,
        ARRAY_AGG(
            IF(
                event_name IN (
                    'session_start', 'view_item', 'add_to_cart',
                    'begin_checkout', 'purchase'
                ),
                STRUCT(event_name, event_timestamp_micros),
                NULL
            ) IGNORE NULLS ORDER BY event_timestamp_micros
        ) AS funnel_events,
        COUNT(*) AS event_count,
        COUNTIF(event_name = 'session_start') AS session_start_events,
        COUNTIF(event_name = 'view_item') AS view_item_events,
        COUNTIF(event_name = 'add_to_cart') AS add_to_cart_events,
        COUNTIF(event_name = 'begin_checkout') AS begin_checkout_events,
        COUNTIF(event_name = 'purchase') AS purchase_events,
        COUNTIF(event_name = 'purchase' AND purchase_revenue_usd IS NULL)
            AS purchase_events_missing_revenue,
        SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0))
            AS purchase_revenue_usd
    FROM valid_events
    GROUP BY user_pseudo_id, ga_session_id
),

ordered_session_start AS (
    SELECT
        *,
        (
            SELECT MIN(step.event_timestamp_micros)
            FROM UNNEST(funnel_events) AS step
            WHERE step.event_name = 'session_start'
        ) AS ordered_session_start_micros
    FROM grouped_sessions
),

ordered_view_item AS (
    SELECT
        *,
        (
            SELECT MIN(step.event_timestamp_micros)
            FROM UNNEST(funnel_events) AS step
            WHERE
                step.event_name = 'view_item'
                AND step.event_timestamp_micros > ordered_session_start_micros
        ) AS ordered_view_item_micros
    FROM ordered_session_start
),

ordered_add_to_cart AS (
    SELECT
        *,
        (
            SELECT MIN(step.event_timestamp_micros)
            FROM UNNEST(funnel_events) AS step
            WHERE
                step.event_name = 'add_to_cart'
                AND step.event_timestamp_micros > ordered_view_item_micros
        ) AS ordered_add_to_cart_micros
    FROM ordered_view_item
),

ordered_begin_checkout AS (
    SELECT
        *,
        (
            SELECT MIN(step.event_timestamp_micros)
            FROM UNNEST(funnel_events) AS step
            WHERE
                step.event_name = 'begin_checkout'
                AND step.event_timestamp_micros > ordered_add_to_cart_micros
        ) AS ordered_begin_checkout_micros
    FROM ordered_add_to_cart
),

ordered_purchase AS (
    SELECT
        *,
        (
            SELECT MIN(step.event_timestamp_micros)
            FROM UNNEST(funnel_events) AS step
            WHERE
                step.event_name = 'purchase'
                AND step.event_timestamp_micros > ordered_begin_checkout_micros
        ) AS ordered_purchase_micros
    FROM ordered_begin_checkout
)

SELECT
    session.user_pseudo_id,
    session.ga_session_id,
    session.session_start_date,
    session.first_event_timestamp_micros,
    session.first_event_dimensions.device_category,
    session.first_event_dimensions.country,
    session.first_event_dimensions.first_touch_source,
    session.first_event_dimensions.first_touch_medium,
    session.event_count,
    session.session_start_events,
    session.view_item_events,
    session.add_to_cart_events,
    session.begin_checkout_events,
    session.purchase_events,
    session.purchase_events_missing_revenue,
    session.purchase_revenue_usd,
    first_visit_users.user_pseudo_id IS NOT NULL AS is_new_user_in_window,
    session.session_start_events > 0 AS has_session_start,
    session.view_item_events > 0 AS has_view_item,
    session.add_to_cart_events > 0 AS has_add_to_cart,
    session.begin_checkout_events > 0 AS has_begin_checkout,
    session.purchase_events > 0 AS has_purchase,
    session.ordered_session_start_micros IS NOT NULL AS ordered_session_start,
    session.ordered_view_item_micros IS NOT NULL AS ordered_view_item,
    session.ordered_add_to_cart_micros IS NOT NULL AS ordered_add_to_cart,
    session.ordered_begin_checkout_micros IS NOT NULL AS ordered_begin_checkout,
    session.ordered_purchase_micros IS NOT NULL AS ordered_purchase
FROM ordered_purchase AS session
LEFT JOIN first_visit_users
    ON session.user_pseudo_id = first_visit_users.user_pseudo_id
