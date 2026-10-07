-- One row per item on an exported event; preserve unmatched purchase items.
SELECT
    {{ ga4_source_event_date('event.event_date') }} AS event_date,
    event.event_timestamp AS event_timestamp_micros,
    event.event_bundle_sequence_id,
    event.event_name,
    event.user_pseudo_id,
    (
        SELECT ANY_VALUE(param.value.int_value)
        FROM UNNEST(event.event_params) AS param
        WHERE param.key = 'ga_session_id'
    ) AS ga_session_id,
    event.device.category AS device_category,
    event.geo.country,
    item_offset,
    item.item_id,
    item.item_name,
    item.item_category,
    item.item_category2,
    item.item_brand,
    item.quantity,
    {{ dbt.safe_cast('item.price_in_usd', dbt.type_numeric()) }} AS item_price_usd,
    {{ dbt.safe_cast('item.item_revenue_in_usd', dbt.type_numeric()) }}
        AS item_revenue_usd
FROM {{ ga4_events_source() }} AS event
CROSS JOIN UNNEST(event.items) AS item WITH OFFSET AS item_offset
