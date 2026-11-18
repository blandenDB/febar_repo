-- title: Explanation generation coverage
SELECT COUNT(*) AS top1_recommendations, COUNT(NULLIF(TRIM(explanation), '')) AS non_empty_explanations,
       SUM(IF(generation_error IS NOT NULL, 1, 0)) AS generation_errors,
       ROUND(AVG(SIZE(SPLIT(explanation, ' '))), 1) AS avg_words,
       MAX(SIZE(SPLIT(explanation, ' '))) AS max_words, MIN(llm_endpoint) AS llm_endpoint
FROM c360_bank.customer_lifetime_value.gold_recommendation_explanations
;
-- title: Grounding checks (counts of explanations that break a rule)
SELECT
  SUM(IF(explanation RLIKE '[0-9]+(\\.[0-9]+)?\\s?%', 1, 0)) AS mentions_a_percentage,
  SUM(IF(explanation RLIKE '\\$\\s?[0-9]' AND NOT EXISTS(signals, s -> s LIKE '%$%'), 1, 0)) AS dollar_amount_not_in_facts,
  SUM(IF(LOWER(explanation) RLIKE 'promotion|special offer|bonus|limited time|apr|interest rate of', 1, 0)) AS mentions_offer_or_rate,
  SUM(IF(LOWER(explanation) RLIKE 'model|score|probabilit|propensity|lifetime value', 1, 0)) AS mentions_model_internals,
  SUM(IF(explanation NOT RLIKE '(?s)^Why: .+\\nOpener: ".+\\?"', 1, 0)) AS not_in_why_opener_format,
  SUM(IF(explanation NOT LIKE '%?%', 1, 0)) AS no_opening_question
FROM c360_bank.customer_lifetime_value.gold_recommendation_explanations
;
-- title: Sample explanations (synthetic customers), one per product
SELECT product, CONCAT_WS(' | ', signals) AS facts_given, explanation
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY product ORDER BY customer_360_id) AS rn
      FROM c360_bank.customer_lifetime_value.gold_recommendation_explanations)
WHERE rn = 1 ORDER BY product
;
-- title: Row filter on explanations
SELECT table_name, filter_name FROM c360_bank.information_schema.row_filters
WHERE table_schema = 'customer_lifetime_value' AND table_name = 'gold_recommendation_explanations'
