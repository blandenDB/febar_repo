-- title: CLV assumptions used (illustrative, see DECISIONS.md)
SELECT * FROM c360_bank.customer_lifetime_value.clv_product_assumptions ORDER BY product
;
SELECT parameter, value FROM c360_bank.customer_lifetime_value.clv_parameters ORDER BY parameter
;
-- title: CLV by segment and number of products
SELECT segment, LEAST(active_products, 4) AS products_capped_at_4, COUNT(*) AS customers,
       ROUND(AVG(annual_margin), 0) AS avg_annual_margin, ROUND(AVG(retention_rate), 2) AS retention,
       ROUND(AVG(clv), 0) AS avg_clv
FROM c360_bank.customer_lifetime_value.gold_customer_clv
GROUP BY 1, 2 ORDER BY 1, 2
;
-- title: Recommendations: customers covered and #1 product mix
SELECT product, COUNT(*) AS customers_with_this_as_top1, ROUND(AVG(propensity), 4) AS avg_propensity,
       ROUND(AVG(lift_vs_base_rate), 1) AS avg_lift_vs_base, ROUND(AVG(clv_uplift_if_adopted), 0) AS avg_clv_uplift_if_adopted,
       ROUND(SUM(expected_clv_uplift), 0) AS total_expected_clv_uplift
FROM c360_bank.customer_lifetime_value.gold_cross_sell_recommendations WHERE recommendation_rank = 1
GROUP BY product ORDER BY customers_with_this_as_top1 DESC
;
-- title: Sample recommendations with supporting signals (synthetic customers)
SELECT customer_360_id, recommendation_rank AS rnk, product, ROUND(propensity, 4) AS propensity,
       ROUND(lift_vs_base_rate, 1) AS lift, ROUND(clv_current, 0) AS clv_now, ROUND(clv_with_product, 0) AS clv_with,
       CONCAT_WS(' | ', signals) AS signals
FROM c360_bank.customer_lifetime_value.gold_cross_sell_recommendations
WHERE customer_360_id IN (SELECT customer_360_id FROM c360_bank.customer_lifetime_value.gold_cross_sell_recommendations
                          WHERE recommendation_rank = 1 ORDER BY expected_clv_uplift DESC LIMIT 3)
ORDER BY customer_360_id, rnk
;
-- title: Row filter attached to the new tables
SELECT table_name, filter_name FROM c360_bank.information_schema.row_filters
WHERE table_schema = 'customer_lifetime_value' AND table_name IN ('gold_customer_clv', 'gold_cross_sell_recommendations')
