{% macro query_comment(node) %}
    {% set labels = {
        'app': 'ga4_checkout_funnel',
        'ga4_run': env_var('GA4_RUN_LABEL', 'manual')
    } %}
    {% do return(tojson(labels)) %}
{% endmacro %}
