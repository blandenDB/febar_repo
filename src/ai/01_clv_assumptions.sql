-- CLV assumptions (value-case numbers; see DECISIONS.md, marked [YOUR WORDS]).
-- Illustrative starting values, not sourced benchmarks. Change here and rerun c360_ml.
-- Create if missing, then INSERT OVERWRITE, so reruns are idempotent.

CREATE TABLE IF NOT EXISTS c360_bank.customer_lifetime_value.clv_product_assumptions (
  product               STRING        COMMENT 'Product name, as in gold_product_holdings.product',
  margin_pct_of_balance DECIMAL(6,4)  COMMENT 'Annual margin as a fraction of balance (0.015 = 1.5%)',
  margin_pct_of_spend   DECIMAL(6,4)  COMMENT 'Annual margin as a fraction of annual card spend (cards only)',
  annual_fee_income     DECIMAL(10,2) COMMENT 'Flat annual fee income per customer holding the product, USD'
)
COMMENT 'Illustrative annual margin assumptions per product used to compute customer lifetime value';

INSERT OVERWRITE c360_bank.customer_lifetime_value.clv_product_assumptions
SELECT * FROM VALUES
  ('checking',      0.0200, 0.0000, 60.00),
  ('savings',       0.0150, 0.0000,  0.00),
  ('cd',            0.0100, 0.0000,  0.00),
  ('money_market',  0.0125, 0.0000,  0.00),
  ('mortgage',      0.0100, 0.0000,  0.00),
  ('auto_loan',     0.0200, 0.0000,  0.00),
  ('heloc',         0.0250, 0.0000,  0.00),
  ('personal_loan', 0.0400, 0.0000,  0.00),
  ('credit_card',   0.1000, 0.0150,  0.00)
  AS t(product, margin_pct_of_balance, margin_pct_of_spend, annual_fee_income);

CREATE TABLE IF NOT EXISTS c360_bank.customer_lifetime_value.clv_parameters (
  parameter STRING        COMMENT 'Parameter name',
  value     DECIMAL(10,4) COMMENT 'Parameter value',
  note      STRING        COMMENT 'What it means'
)
COMMENT 'Illustrative lifetime assumptions used to compute customer lifetime value';

INSERT OVERWRITE c360_bank.customer_lifetime_value.clv_parameters
SELECT * FROM VALUES
  ('retention_1_product',  0.8500, 'Annual retention for customers with 0 or 1 active product'),
  ('retention_2_products', 0.9000, 'Annual retention for customers with 2 active products'),
  ('retention_3_plus',     0.9400, 'Annual retention for customers with 3 or more active products'),
  ('horizon_years',       10.0000, 'Years of margin counted in CLV'),
  ('discount_rate',        0.0800, 'Annual discount rate applied to future margin')
  AS t(parameter, value, note);
