-- Aggregate the actual daily table at the independently saved segment grain.
SELECT
    device_category,
    country,
    funnel_mode,
    step_order,
    MIN(step_name) AS step_name,
    SUM(total_sessions) AS total_sessions,
    SUM(reached_sessions) AS reached_sessions
FROM __fct_funnel_daily__
GROUP BY device_category, country, funnel_mode, step_order;
