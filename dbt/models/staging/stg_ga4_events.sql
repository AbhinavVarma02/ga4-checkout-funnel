-- One row per exported event; never unnest items in this model.
SELECT
    {{ ga4_source_event_date('event.event_date') }} AS event_date,
    event.event_date AS event_date_raw,
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
    event.traffic_source.source AS first_touch_source,
    event.traffic_source.medium AS first_touch_medium,
    event.traffic_source.name AS first_touch_campaign,
    (
        SELECT ANY_VALUE(param.value.string_value)
        FROM UNNEST(event.event_params) AS param
        WHERE param.key = 'source'
    ) AS event_param_source,
    (
        SELECT ANY_VALUE(param.value.string_value)
        FROM UNNEST(event.event_params) AS param
        WHERE param.key = 'medium'
    ) AS event_param_medium,
    event.ecommerce.transaction_id,
    {{ dbt.safe_cast('event.ecommerce.purchase_revenue_in_usd', dbt.type_numeric()) }}
        AS purchase_revenue_usd,
    ARRAY_LENGTH(event.items) AS item_rows
FROM {{ ga4_events_source() }} AS event
