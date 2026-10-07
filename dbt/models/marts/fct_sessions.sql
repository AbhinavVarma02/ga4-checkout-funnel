{{ ga4_mart_config() }}
{% set refresh_dates = ga4_refresh_dates() %}
-- One session row for BI; channel columns are explicitly first-touch.
SELECT
    user_pseudo_id,
    ga_session_id,
    session_start_date,
    first_event_timestamp_micros,
    device_category,
    country,
    first_touch_source,
    first_touch_medium,
    event_count,
    session_start_events,
    view_item_events,
    add_to_cart_events,
    begin_checkout_events,
    purchase_events,
    purchase_events_missing_revenue,
    purchase_revenue_usd,
    has_session_start,
    has_view_item,
    has_add_to_cart,
    has_begin_checkout,
    has_purchase,
    ordered_session_start,
    ordered_view_item,
    ordered_add_to_cart,
    ordered_begin_checkout,
    ordered_purchase,
    CONCAT(
        COALESCE(first_touch_source, '(not set)'),
        ' / ',
        COALESCE(first_touch_medium, '(not set)')
    ) AS first_touch_channel,
    CASE
        WHEN is_new_user_in_window THEN 'new_in_window'
        ELSE 'no_observed_first_visit'
    END AS user_cohort
FROM {{ ref('int_sessions') }}

{% if ga4_is_replay() and is_incremental() %}
WHERE session_start_date IN ({{ refresh_dates }})
{% endif %}
