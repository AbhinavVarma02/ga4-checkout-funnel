-- Placeholder uses the compiled event SELECT or the approved existing event view.
WITH source_daily AS (
    SELECT
        PARSE_DATE('%Y%m%d', event_date) AS event_date,
        COUNT(*) AS source_events,
        COUNTIF(event_name = 'purchase') AS source_purchase_events,
        SUM(IF(
            event_name = 'purchase',
            COALESCE(CAST(ecommerce.purchase_revenue_in_usd AS BIGNUMERIC), 0), 0
        ))
            AS source_revenue_usd
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
    WHERE _table_suffix BETWEEN '20201101' AND '20210131'
    GROUP BY event_date
),

staged_daily AS (
    SELECT
        event_date,
        COUNT(*) AS staged_events,
        COUNTIF(event_name = 'purchase') AS staged_purchase_events,
        SUM(IF(event_name = 'purchase', COALESCE(purchase_revenue_usd, 0), 0))
            AS staged_revenue_usd
    FROM __event_model__
    GROUP BY event_date
)

SELECT
    public_day.source_events,
    staged.staged_events,
    public_day.source_purchase_events,
    staged.staged_purchase_events,
    public_day.source_revenue_usd,
    staged.staged_revenue_usd,
    COALESCE(public_day.event_date, staged.event_date) AS event_date
FROM source_daily AS public_day
FULL OUTER JOIN staged_daily AS staged ON public_day.event_date = staged.event_date
ORDER BY event_date;
