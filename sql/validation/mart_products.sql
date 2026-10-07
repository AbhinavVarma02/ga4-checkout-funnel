-- Session start dates are disjoint; product reach can be summed across dates.
SELECT
    item_id,
    item_category,
    MIN(item_name) AS item_name,
    SUM(viewing_sessions) AS viewing_sessions,
    SUM(purchasing_sessions) AS purchasing_sessions,
    SUM(view_and_purchase_sessions) AS view_and_purchase_sessions,
    SUM(purchase_without_view_sessions) AS purchase_without_view_sessions,
    SUM(null_purchase_item_revenue_rows) AS null_purchase_item_revenue_rows,
    SUM(purchase_item_revenue_usd) AS purchase_item_revenue_usd
FROM __fct_product_daily__
GROUP BY item_id, item_category;
