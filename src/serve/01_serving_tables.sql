-- Serving copies of the gold tables for Lakebase sync.
-- UC does not allow syncing tables with row filters or column masks, so these are
-- unmasked copies built by the data owner. They are granted to no persona in UC, and
-- access in Lakebase is enforced by Postgres row-level security (src/serve/02_postgres_setup.sql).
-- CREATE OR REPLACE keeps reruns idempotent.

-- App roster: which bankers (app users) serve which branches. Separate from
-- c360_access_entitlements so app access never changes Lakehouse access.
CREATE TABLE IF NOT EXISTS c360_bank.customer_lifetime_value.c360_banker_assignments (
  banker_principal STRING NOT NULL COMMENT 'App user identity (email) as the Databricks App forwards it',
  branch_ids ARRAY<STRING> NOT NULL COMMENT 'Branches this banker serves in the app',
  updated_at TIMESTAMP COMMENT 'When the assignment was last set'
)
COMMENT 'Relationship banker branch assignments used by Postgres row-level security in the app';

-- Demo assignment: the person deploying the build serves branches BR001 and BR002 in the app.
MERGE INTO c360_bank.customer_lifetime_value.c360_banker_assignments t
USING (SELECT current_user() AS banker_principal) s ON t.banker_principal = s.banker_principal
WHEN MATCHED THEN UPDATE SET branch_ids = ARRAY('BR001', 'BR002'), updated_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (banker_principal, branch_ids, updated_at)
  VALUES (s.banker_principal, ARRAY('BR001', 'BR002'), current_timestamp());

CREATE OR REPLACE TABLE c360_bank.serving.serving_customer_360
COMMENT 'Owner-only serving copy of gold_customer_360 for Lakebase sync (access enforced by Postgres RLS)'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT customer_360_id, first_name, last_name, email, city, state, zip, age, segment, home_branch_id,
          customer_since, tenure_years, active_products, has_checking, has_savings, has_cd, has_money_market,
          has_mortgage, has_auto_loan, has_heloc, has_personal_loan, has_credit_card,
          CAST(total_deposit_balance AS DOUBLE) AS total_deposit_balance,
          CAST(total_loan_balance AS DOUBLE) AS total_loan_balance,
          CAST(total_card_balance AS DOUBLE) AS total_card_balance,
          CAST(card_spend_12m AS DOUBLE) AS card_spend_12m, is_digitally_enrolled, digital_events_90d,
          last_digital_activity_ts
   FROM c360_bank.customer_lifetime_value.gold_customer_360
   WHERE home_branch_id IS NOT NULL;

CREATE OR REPLACE TABLE c360_bank.serving.serving_product_holdings
COMMENT 'Owner-only serving copy of gold_product_holdings for Lakebase sync (access enforced by Postgres RLS)'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT account_id, customer_360_id, home_branch_id, source_system, product, product_variant, open_date,
          CAST(balance AS DOUBLE) AS balance, CAST(credit_limit AS DOUBLE) AS credit_limit,
          CAST(interest_rate AS DOUBLE) AS interest_rate, status
   FROM c360_bank.customer_lifetime_value.gold_product_holdings
   WHERE home_branch_id IS NOT NULL;

CREATE OR REPLACE TABLE c360_bank.serving.serving_recommendations
COMMENT 'Owner-only serving copy of recommendations plus the #1 explanation, for Lakebase sync (access enforced by Postgres RLS)'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT CONCAT(r.customer_360_id, '-', r.recommendation_rank) AS recommendation_id,
          r.customer_360_id, r.home_branch_id, r.recommendation_rank, r.product, r.propensity, r.lift_vs_base_rate,
          r.product_annual_margin, r.clv_current, r.clv_with_product, r.clv_uplift_if_adopted, r.expected_clv_uplift,
          CONCAT_WS(' | ', r.signals) AS signals, e.explanation, r.model_version, r.as_of_date
   FROM c360_bank.customer_lifetime_value.gold_cross_sell_recommendations r
   LEFT JOIN c360_bank.customer_lifetime_value.gold_recommendation_explanations e
     ON e.customer_360_id = r.customer_360_id AND r.recommendation_rank = 1
   WHERE r.home_branch_id IS NOT NULL;

CREATE OR REPLACE TABLE c360_bank.serving.serving_banker_assignments
COMMENT 'Owner-only serving copy of c360_banker_assignments for Lakebase sync (drives Postgres RLS)'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT banker_principal, branch_ids FROM c360_bank.customer_lifetime_value.c360_banker_assignments;

ALTER TABLE c360_bank.serving.serving_customer_360 SET TAGS ('data_classification' = 'pii');
ALTER TABLE c360_bank.serving.serving_customer_360 ALTER COLUMN first_name SET TAGS ('c360_pii_type' = 'name');
ALTER TABLE c360_bank.serving.serving_customer_360 ALTER COLUMN last_name SET TAGS ('c360_pii_type' = 'name');
ALTER TABLE c360_bank.serving.serving_customer_360 ALTER COLUMN email SET TAGS ('c360_pii_type' = 'email');
