-- Calendar coverage follows the selected source suffix window.
SELECT
    date_day,
    EXTRACT(YEAR FROM date_day) AS calendar_year,
    EXTRACT(MONTH FROM date_day) AS calendar_month,
    EXTRACT(DAY FROM date_day) AS calendar_day,
    EXTRACT(DAYOFWEEK FROM date_day) AS day_of_week_sunday_first
FROM {{ ga4_date_spine(var('start_suffix'), var('end_suffix')) }} AS date_day
