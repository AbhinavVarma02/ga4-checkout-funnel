{{ ga4_mart_config() }}
{% set refresh_dates = ga4_refresh_dates() %}
-- Cumulative reach at start-date x device x country x mode x step grain.
WITH session_steps AS (
    SELECT
        session.session_start_date,
        session.device_category,
        session.country,
        session.has_purchase,
        session.purchase_revenue_usd,
        step.funnel_mode,
        step.step_order,
        step.step_name,
        step.reached
    FROM {{ ref('fct_sessions') }} AS session
    CROSS JOIN
        UNNEST([
            STRUCT(
                'any_order' AS funnel_mode, 1 AS step_order,
                'session_start' AS step_name, session.has_session_start AS reached
            ),
            STRUCT(
                'any_order', 2, 'view_item',
                session.has_session_start AND session.has_view_item
            ),
            STRUCT(
                'any_order', 3, 'add_to_cart',
                session.has_session_start AND session.has_view_item
                AND session.has_add_to_cart
            ),
            STRUCT(
                'any_order', 4, 'begin_checkout',
                session.has_session_start AND session.has_view_item
                AND session.has_add_to_cart AND session.has_begin_checkout
            ),
            STRUCT(
                'any_order', 5, 'purchase',
                session.has_session_start AND session.has_view_item
                AND session.has_add_to_cart AND session.has_begin_checkout
                AND session.has_purchase
            ),
            STRUCT('strict_ordered', 1, 'session_start', session.ordered_session_start),
            STRUCT('strict_ordered', 2, 'view_item', session.ordered_view_item),
            STRUCT('strict_ordered', 3, 'add_to_cart', session.ordered_add_to_cart),
            STRUCT('strict_ordered', 4, 'begin_checkout', session.ordered_begin_checkout),
            STRUCT('strict_ordered', 5, 'purchase', session.ordered_purchase)
        ]) AS step
    {% if ga4_is_replay() and is_incremental() %}
    WHERE session.session_start_date IN ({{ refresh_dates }})
    {% endif %}
),

daily_reach AS (
    SELECT
        session_start_date,
        device_category,
        country,
        funnel_mode,
        step_order,
        step_name,
        COUNT(*) AS total_sessions,
        COUNTIF(reached) AS reached_sessions,
        COUNTIF(reached AND has_purchase) AS purchased_sessions_among_reached,
        SUM(IF(reached, purchase_revenue_usd, 0))
            AS purchase_revenue_usd_among_reached
    FROM session_steps
    GROUP BY
        session_start_date, device_category, country,
        funnel_mode, step_order, step_name
)

SELECT
    *,
    LEAD(reached_sessions) OVER (
        PARTITION BY session_start_date, device_category, country, funnel_mode
        ORDER BY step_order
    ) AS next_step_reached_sessions,
    LEAD(purchased_sessions_among_reached) OVER (
        PARTITION BY session_start_date, device_category, country, funnel_mode
        ORDER BY step_order
    ) AS next_step_purchased_sessions
FROM daily_reach
