{% test unique_session_pair(model, user_column, session_column) %}
    SELECT
        {{ user_column }},
        {{ session_column }},
        COUNT(*) AS duplicate_rows
    FROM {{ model }}
    GROUP BY {{ user_column }}, {{ session_column }}
    HAVING COUNT(*) > 1
{% endtest %}
