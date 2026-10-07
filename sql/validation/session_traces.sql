-- Seeded random selection within disjoint diagnostic strata, not population estimates.
WITH sessions AS (
    SELECT * FROM __session_model__
),

events AS (
    SELECT * FROM __event_model__
),

date_counts AS (
    SELECT
        user_pseudo_id,
        ga_session_id,
        COUNT(DISTINCT event_date) AS export_dates
    FROM events
    GROUP BY user_pseudo_id, ga_session_id
),

candidates AS (
    SELECT
        session.*,
        CASE
            WHEN dates.export_dates > 1 THEN 'cross_midnight'
            WHEN
                session.has_session_start AND session.has_view_item
                AND session.has_add_to_cart AND session.has_begin_checkout
                AND session.has_purchase AND NOT session.ordered_purchase
                THEN 'any_order_purchase_only'
            WHEN session.ordered_purchase THEN 'strict_purchase'
            WHEN NOT session.has_session_start THEN 'missing_session_start'
            ELSE 'other_sessions'
        END AS sample_stratum,
        TO_HEX(SHA256(CONCAT(
            'breadcrumb-trace-20261004:',
            TO_JSON_STRING(STRUCT(session.user_pseudo_id, session.ga_session_id))
        ))) AS sample_hash
    FROM sessions AS session
    INNER JOIN
        date_counts AS dates
        ON
            session.user_pseudo_id = dates.user_pseudo_id
            AND session.ga_session_id = dates.ga_session_id
),

sample AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY sample_stratum) AS eligible_sessions
    FROM candidates
    QUALIFY ROW_NUMBER() OVER (PARTITION BY sample_stratum ORDER BY sample_hash) = 1
)

SELECT
    sample.sample_stratum,
    sample.sample_hash,
    sample.eligible_sessions,
    sample.session_start_date,
    sample.device_category,
    sample.country,
    sample.event_count,
    sample.purchase_events,
    sample.purchase_revenue_usd,
    sample.has_session_start,
    sample.has_view_item,
    sample.has_add_to_cart,
    sample.has_begin_checkout,
    sample.has_purchase,
    sample.ordered_session_start,
    sample.ordered_view_item,
    sample.ordered_add_to_cart,
    sample.ordered_begin_checkout,
    sample.ordered_purchase,
    ARRAY_AGG(STRUCT(
        event.event_date,
        event.event_timestamp_micros,
        event.event_name,
        event.purchase_revenue_usd
    ) ORDER BY event.event_timestamp_micros, event.event_name) AS event_trace
FROM sample
INNER JOIN events AS event
    ON
        sample.user_pseudo_id = event.user_pseudo_id
        AND sample.ga_session_id = event.ga_session_id
GROUP BY ALL
ORDER BY sample.sample_stratum;
