-- Banker-facing explanation for each customer's #1 recommendation, written by a
-- foundation model from the listed facts only. CREATE OR REPLACE keeps reruns idempotent;
-- the row filter and comments are reapplied afterwards.

CREATE OR REPLACE TABLE c360_bank.customer_lifetime_value.gold_recommendation_explanations
COMMENT 'Short, fact-grounded explanation for each customer''s #1 cross-sell recommendation, written by databricks-claude-haiku-5-5'
AS
WITH top1 AS (
  SELECT r.customer_360_id, r.home_branch_id, r.product, r.propensity, r.clv_uplift_if_adopted, r.signals,
         CASE r.product WHEN 'savings' THEN 'savings account' WHEN 'cd' THEN 'certificate of deposit'
              WHEN 'money_market' THEN 'money market account' WHEN 'mortgage' THEN 'mortgage'
              WHEN 'auto_loan' THEN 'auto loan' WHEN 'heloc' THEN 'home equity line of credit'
              WHEN 'personal_loan' THEN 'personal loan' WHEN 'credit_card' THEN 'credit card' END AS product_name
  FROM c360_bank.customer_lifetime_value.gold_cross_sell_recommendations r
  WHERE r.recommendation_rank = 1
),
prompts AS (
  SELECT *, CONCAT(
    'You are briefing a relationship banker at a regional bank before a customer conversation. ',
    'Recommended product: ', product_name, '. ',
    'Facts about the customer (use only these; do not invent rates, fees, promotions, amounts or any other details): ',
    CONCAT_WS('; ', signals), '. ',
    'Reply in exactly this format and nothing else:\n',
    'Why: <one or two sentences to the banker explaining why this product fits; refer to the person as "the customer">\n',
    'Opener: "<one natural, non-pushy question the banker could ask the customer>"\n',
    'Do not use the customer''s name. Do not mention models, scores, probabilities or lifetime value.') AS prompt
  FROM top1
),
gen AS (
  SELECT *, ai_query('databricks-claude-haiku-5-5', prompt,
                     modelParameters => named_struct('max_tokens', 1000),
                     failOnError => false) AS response
  FROM prompts
)
SELECT customer_360_id, home_branch_id, product, propensity, clv_uplift_if_adopted, signals,
       NULLIF(TRIM(response.result), '') AS explanation, response.errorMessage AS generation_error,
       'databricks-claude-haiku-5-5' AS llm_endpoint, current_timestamp() AS generated_at
FROM gen;

ALTER TABLE c360_bank.customer_lifetime_value.gold_recommendation_explanations
  SET ROW FILTER c360_bank.customer_lifetime_value.c360_branch_filter ON (home_branch_id);

ALTER TABLE c360_bank.customer_lifetime_value.gold_recommendation_explanations
  ALTER COLUMN explanation COMMENT 'Banker-facing explanation and opening question, generated only from the signals column';
ALTER TABLE c360_bank.customer_lifetime_value.gold_recommendation_explanations
  ALTER COLUMN signals COMMENT 'Facts given to the model; the explanation must not go beyond these';

-- Fail the task (and the job) if more than 5% of generations errored, so a silent
-- failure cannot pass as a successful run.
SELECT IF(SUM(IF(explanation IS NULL, 1, 0)) > 0.05 * COUNT(*),
          raise_error(CONCAT('Explanation generation failed for ', SUM(IF(explanation IS NULL, 1, 0)), ' of ', COUNT(*), ' rows')),
          CONCAT('ok: ', COUNT(explanation), ' of ', COUNT(*), ' explanations generated')) AS generation_check
FROM c360_bank.customer_lifetime_value.gold_recommendation_explanations;
