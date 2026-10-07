{% macro ga4_public_events() %}
    (
        SELECT *
        FROM {{ source('ga4_public', 'events') }}
        WHERE _TABLE_SUFFIX BETWEEN '{{ var('start_suffix') }}' AND '{{ var('end_suffix') }}'
    )
{% endmacro %}
