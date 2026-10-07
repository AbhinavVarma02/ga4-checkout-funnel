{% macro ga4_parse_event_date(expression) %}
    {{ return(adapter.dispatch('ga4_parse_event_date', 'ga4_checkout_funnel')(expression)) }}
{% endmacro %}

{% macro bigquery__ga4_parse_event_date(expression) %}
    PARSE_DATE('%Y%m%d', {{ expression }})
{% endmacro %}

{% macro default__ga4_parse_event_date(expression) %}
    {{ exceptions.raise_compiler_error('GA4 YYYYMMDD parsing is not implemented for this adapter') }}
{% endmacro %}

{% macro ga4_date_spine(start_suffix, end_suffix) %}
    {{ return(adapter.dispatch('ga4_date_spine', 'ga4_checkout_funnel')(start_suffix, end_suffix)) }}
{% endmacro %}

{% macro bigquery__ga4_date_spine(start_suffix, end_suffix) %}
    UNNEST(GENERATE_DATE_ARRAY(
        PARSE_DATE('%Y%m%d', '{{ start_suffix }}'),
        PARSE_DATE('%Y%m%d', '{{ end_suffix }}')
    ))
{% endmacro %}

{% macro default__ga4_date_spine(start_suffix, end_suffix) %}
    {{ exceptions.raise_compiler_error('GA4 date spine is not implemented for this adapter') }}
{% endmacro %}
