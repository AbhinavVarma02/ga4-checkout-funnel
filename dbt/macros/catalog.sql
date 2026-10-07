{% macro bigquery__get_catalog_relations(information_schema, relations) %}
    {# The pinned adapter filters date shards before it restores their wildcard. #}
    {% set filter_relations = [] %}
    {% for relation in relations %}
        {% if relation.database == 'bigquery-public-data'
            and relation.schema == 'ga4_obfuscated_sample_ecommerce'
            and relation.identifier == 'events_*' %}
            {% do filter_relations.append(relation.incorporate(path={'identifier': 'events_'})) %}
        {% else %}
            {% do filter_relations.append(relation) %}
        {% endif %}
    {% endfor %}
    {{ return(dbt.bigquery__get_catalog_relations(information_schema, filter_relations)) }}
{% endmacro %}
