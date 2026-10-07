{{ ga4_mart_config() }}
{% set refresh_dates = ga4_refresh_dates() %}
-- Product reach at session-start day x device x country x item x category.
WITH item_sessions AS (
    SELECT
        session.session_start_date,
        session.device_category,
        session.country,
        item.item_id,
        item.item_category,
        item.user_pseudo_id,
        item.ga_session_id,
        MIN(item.item_name) AS item_name,
        COUNTIF(item.event_name = 'view_item') > 0 AS viewed_item,
        COUNTIF(item.event_name = 'purchase') > 0 AS purchased_item,
        COUNTIF(item.event_name = 'purchase' AND item.item_revenue_usd IS NULL)
            AS null_purchase_item_revenue_rows,
        SUM(IF(item.event_name = 'purchase', COALESCE(item.item_revenue_usd, 0), 0))
            AS purchase_item_revenue_usd
    FROM {{ ref('stg_ga4_items') }} AS item
    INNER JOIN {{ ref('int_sessions') }} AS session
        ON
            item.user_pseudo_id = session.user_pseudo_id
            AND item.ga_session_id = session.ga_session_id
    WHERE item.event_name IN ('view_item', 'purchase')
    {% if ga4_is_replay() and is_incremental() %}
        AND session.session_start_date IN ({{ refresh_dates }})
    {% endif %}
    GROUP BY
        session.session_start_date, session.device_category, session.country,
        item.item_id, item.item_category,
        item.user_pseudo_id, item.ga_session_id
)

SELECT
    session_start_date,
    device_category,
    country,
    item_id,
    item_category,
    MIN(item_name) AS item_name,
    COUNTIF(viewed_item) AS viewing_sessions,
    COUNTIF(purchased_item) AS purchasing_sessions,
    COUNTIF(viewed_item AND purchased_item) AS view_and_purchase_sessions,
    COUNTIF(purchased_item AND NOT viewed_item) AS purchase_without_view_sessions,
    SUM(null_purchase_item_revenue_rows) AS null_purchase_item_revenue_rows,
    SUM(purchase_item_revenue_usd) AS purchase_item_revenue_usd
FROM item_sessions
GROUP BY session_start_date, device_category, country, item_id, item_category
