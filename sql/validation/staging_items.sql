-- Validate actual staging item grain and USD fields against saved source output.
SELECT
    event_name,
    COUNT(*) AS item_rows,
    COUNTIF(item_id IS NULL) AS null_item_id_rows,
    COUNTIF(item_name IS NULL) AS null_item_name_rows,
    COUNTIF(item_category IS NULL) AS null_item_category_rows,
    COUNTIF(item_revenue_usd IS NULL) AS null_item_revenue_usd_rows,
    SUM(CAST(item_revenue_usd AS BIGNUMERIC)) AS item_revenue_usd_sum
FROM __items_model__
GROUP BY event_name
ORDER BY event_name;
