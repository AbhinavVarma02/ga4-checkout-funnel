-- Return any strict-ordered step whose reach exceeds its previous step.
WITH steps AS (
    SELECT
        session_start_date,
        device_category,
        country,
        step_order,
        reached_sessions,
        LAG(reached_sessions) OVER (
            PARTITION BY session_start_date, device_category, country
            ORDER BY step_order
        ) AS previous_step_sessions
    FROM {{ ref('fct_funnel_daily') }}
    WHERE funnel_mode = 'strict_ordered'
)

SELECT *
FROM steps
WHERE
    previous_step_sessions IS NOT NULL
    AND reached_sessions > previous_step_sessions
