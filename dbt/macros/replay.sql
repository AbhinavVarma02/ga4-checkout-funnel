{% macro ga4_is_replay() %}
    {% set mode = var('pipeline_mode', 'sandbox') %}
    {% if mode not in ['sandbox', 'replay'] %}
        {{ exceptions.raise_compiler_error('pipeline_mode must be sandbox or replay') }}
    {% endif %}
    {% if mode == 'replay' %}
        {% set run_date = var('run_date', '') %}
        {% if not modules.re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', run_date) %}
            {{ exceptions.raise_compiler_error('replay requires run_date YYYY-MM-DD') }}
        {% endif %}
        {% set checked_date = modules.datetime.date.fromisoformat(run_date) %}
        {% if run_date < '2020-11-01' or run_date > '2021-01-31' %}
            {{ exceptions.raise_compiler_error('run_date is outside the sample window') }}
        {% endif %}
    {% endif %}
    {{ return(mode == 'replay') }}
{% endmacro %}

{% macro ga4_events_source() %}
    {% if ga4_is_replay() %}
        (
            SELECT * FROM {{ source('ga4_raw', 'events') }}
            WHERE event_date BETWEEN DATE '2020-11-01' AND DATE '2021-01-31'
        )
    {% else %}
        {{ ga4_public_events() }}
    {% endif %}
{% endmacro %}

{% macro ga4_source_event_date(expression) %}
    {% if ga4_is_replay() %}
        {{ expression }}
    {% else %}
        {{ ga4_parse_event_date(expression) }}
    {% endif %}
{% endmacro %}

{% macro ga4_mart_config() %}
    {% if ga4_is_replay() %}
        {{ config(
            materialized='incremental', incremental_strategy='insert_overwrite',
            partition_by={'field': 'session_start_date', 'data_type': 'date', 'granularity': 'day'},
            cluster_by=['device_category', 'country'], on_schema_change='fail',
            full_refresh=false
        ) }}
    {% endif %}
{% endmacro %}

{% macro ga4_refresh_dates() %}
    {% set events = ref('stg_ga4_events') %}
    {% set sessions = ref('int_sessions') %}
    {% if ga4_is_replay() %}
        SELECT DATE '{{ var("run_date") }}' AS session_start_date
        UNION DISTINCT
        SELECT GREATEST(DATE '2020-11-01', DATE_SUB(DATE '{{ var("run_date") }}', INTERVAL 1 DAY))
        UNION DISTINCT
        SELECT DISTINCT session.session_start_date
        FROM {{ sessions }} AS session
        WHERE EXISTS (
            SELECT 1 FROM {{ events }} AS recent
            WHERE recent.event_date BETWEEN
                GREATEST(DATE '2020-11-01', DATE_SUB(DATE '{{ var("run_date") }}', INTERVAL 1 DAY))
                AND DATE '{{ var("run_date") }}'
                AND recent.user_pseudo_id = session.user_pseudo_id
                AND (recent.ga_session_id = session.ga_session_id OR recent.event_name = 'first_visit')
        )
    {% endif %}
{% endmacro %}
