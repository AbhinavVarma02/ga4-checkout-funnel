-- Check complete daily grains and calendar attributes beyond native dbt tests.
WITH calendar AS (
    SELECT date_day
    FROM UNNEST(GENERATE_DATE_ARRAY(DATE '2020-11-01', DATE '2021-01-31')) AS date_day
),

funnel_steps AS (
    SELECT
        *,
        LEAD(reached_sessions) OVER (
            PARTITION BY session_start_date, device_category, country, funnel_mode
            ORDER BY step_order
        ) AS expected_next_reach,
        LEAD(purchased_sessions_among_reached) OVER (
            PARTITION BY session_start_date, device_category, country, funnel_mode
            ORDER BY step_order
        ) AS expected_next_purchase
    FROM __fct_funnel_daily__
)

SELECT
    (
        SELECT COUNT(*) FROM (
            SELECT
                session_start_date,
                device_category,
                country,
                funnel_mode,
                step_order
            FROM __fct_funnel_daily__
            GROUP BY session_start_date, device_category, country, funnel_mode, step_order
            HAVING COUNT(*) != 1
        ) AS duplicates
    ) AS duplicate_funnel_grains,
    (
        SELECT COUNT(*) FROM (
            SELECT
                session_start_date,
                device_category,
                country,
                item_id,
                item_category
            FROM __fct_product_daily__
            GROUP BY session_start_date, device_category, country, item_id, item_category
            HAVING COUNT(*) != 1
        ) AS duplicates
    ) AS duplicate_product_grains,
    (
        SELECT COUNT(*) FROM (
            SELECT date_day FROM __dim_date__
            GROUP BY date_day
            HAVING COUNT(*) != 1
        ) AS duplicates
    ) AS duplicate_dates,
    (
        SELECT COUNT(*) FROM calendar AS expected
        FULL OUTER JOIN __dim_date__ AS actual ON expected.date_day = actual.date_day
        WHERE expected.date_day IS NULL OR actual.date_day IS NULL
    ) AS calendar_coverage_mismatches,
    (
        SELECT COUNT(*) FROM __dim_date__
        WHERE
            calendar_year IS DISTINCT FROM EXTRACT(YEAR FROM date_day)
            OR calendar_month IS DISTINCT FROM EXTRACT(MONTH FROM date_day)
            OR calendar_day IS DISTINCT FROM EXTRACT(DAY FROM date_day)
            OR day_of_week_sunday_first IS DISTINCT FROM EXTRACT(DAYOFWEEK FROM date_day)
    ) AS calendar_attribute_mismatches,
    (
        SELECT COUNT(*) FROM funnel_steps
        WHERE
            next_step_reached_sessions IS DISTINCT FROM expected_next_reach
            OR next_step_purchased_sessions IS DISTINCT FROM expected_next_purchase
            OR purchased_sessions_among_reached > reached_sessions
            OR reached_sessions > total_sessions
            OR next_step_reached_sessions > reached_sessions
    ) AS funnel_reach_or_lead_mismatches,
    (
        SELECT COUNT(*) FROM __fct_product_daily__
        WHERE
            view_and_purchase_sessions > viewing_sessions
            OR view_and_purchase_sessions + purchase_without_view_sessions != purchasing_sessions
    ) AS product_reach_mismatches;
