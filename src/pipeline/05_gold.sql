-- Gold: the customer 360 view.
--   gold_product_holdings          one row per product account, linked to customer_360_id
--   gold_digital_product_interest  product page views / application starts per customer and product
--   gold_customer_360              one row per customer: profile, holdings, balances, activity

CREATE OR REFRESH MATERIALIZED VIEW gold_product_holdings
COMMENT 'Every product account across core banking, loans and cards, linked to its customer_360_id'
AS
SELECT m.customer_360_id, 'core_banking' AS source_system, d.account_id, d.product_type AS product,
       CAST(NULL AS STRING) AS product_variant, d.open_date, d.balance,
       CAST(NULL AS DECIMAL(14,2)) AS credit_limit, CAST(NULL AS DECIMAL(6,3)) AS interest_rate, d.status
FROM silver_deposit_accounts d
JOIN customer_identity_map m ON m.system = 'core_banking' AND m.source_customer_id = d.cb_customer_id
UNION ALL
SELECT m.customer_360_id, 'loans', l.loan_id, l.product_type, CAST(NULL AS STRING), l.origination_date,
       l.current_balance, CAST(NULL AS DECIMAL(14,2)), l.interest_rate, l.status
FROM silver_loans l
JOIN customer_identity_map m ON m.system = 'loans' AND m.source_customer_id = l.ln_customer_id
UNION ALL
SELECT m.customer_360_id, 'cards', c.card_id, 'credit_card', c.product_type, c.open_date,
       c.current_balance, c.credit_limit, CAST(NULL AS DECIMAL(6,3)), c.status
FROM silver_card_accounts c
JOIN customer_identity_map m ON m.system = 'cards' AND m.source_customer_id = c.cc_customer_id;

CREATE OR REFRESH MATERIALIZED VIEW gold_digital_product_interest
COMMENT 'Digital product page views and application starts per customer and product, last 90 days before the as-of date'
AS
SELECT m.customer_360_id, e.product,
       SUM(IF(e.event_type = 'view_product_page', 1, 0)) AS product_views_90d,
       SUM(IF(e.event_type = 'start_application', 1, 0)) AS application_starts_90d,
       MAX(e.event_ts) AS last_interest_ts
FROM silver_digital_events e
JOIN customer_identity_map m ON m.system = 'digital' AND m.source_customer_id = e.dg_user_id
WHERE e.product IS NOT NULL
  AND e.event_ts >= DATE_SUB(DATE '${as_of_date}', 90) AND e.event_ts < DATE_ADD(DATE '${as_of_date}', 1)
GROUP BY m.customer_360_id, e.product;

CREATE OR REFRESH MATERIALIZED VIEW gold_customer_360 (
  CONSTRAINT unique_customer EXPECT (customer_360_id IS NOT NULL)
)
COMMENT 'One row per customer across all four source systems: profile, products held, balances and activity'
AS
WITH ids AS (
  SELECT m.customer_360_id, m.match_rule, i.*,
         CASE i.system WHEN 'core_banking' THEN 0 WHEN 'loans' THEN 1 WHEN 'cards' THEN 2 ELSE 3 END AS pri
  FROM customer_identity_map m
  JOIN silver_customer_identities i USING (system, source_customer_id)
),
base AS (
  SELECT * FROM ids
  QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_360_id ORDER BY pri, source_customer_id) = 1
),
systems AS (
  SELECT customer_360_id, ARRAY_SORT(COLLECT_SET(system)) AS source_systems,
         COUNT(*) AS source_records
  FROM ids GROUP BY customer_360_id
),
holdings AS (
  SELECT customer_360_id,
    COUNT(DISTINCT product)                                              AS active_products,
    MAX(IF(product = 'checking', 1, 0))       AS has_checking,
    MAX(IF(product = 'savings', 1, 0))        AS has_savings,
    MAX(IF(product = 'cd', 1, 0))             AS has_cd,
    MAX(IF(product = 'money_market', 1, 0))   AS has_money_market,
    MAX(IF(product = 'mortgage', 1, 0))       AS has_mortgage,
    MAX(IF(product = 'auto_loan', 1, 0))      AS has_auto_loan,
    MAX(IF(product = 'heloc', 1, 0))          AS has_heloc,
    MAX(IF(product = 'personal_loan', 1, 0))  AS has_personal_loan,
    MAX(IF(product = 'credit_card', 1, 0))    AS has_credit_card,
    SUM(IF(source_system = 'core_banking', balance, 0)) AS total_deposit_balance,
    SUM(IF(source_system = 'loans', balance, 0))        AS total_loan_balance,
    SUM(IF(source_system = 'cards', balance, 0))        AS total_card_balance,
    SUM(IF(source_system = 'cards', credit_limit, 0))   AS total_card_limit,
    MIN(open_date)                                      AS first_product_open_date
  FROM gold_product_holdings
  WHERE status <> 'closed'
  GROUP BY customer_360_id
),
card_spend AS (
  SELECT m.customer_360_id, SUM(t.amount) AS card_spend_12m, COUNT(*) AS card_txns_12m
  FROM silver_card_transactions t
  JOIN silver_card_accounts a USING (card_id)
  JOIN customer_identity_map m ON m.system = 'cards' AND m.source_customer_id = a.cc_customer_id
  WHERE t.txn_ts >= DATE_SUB(DATE '${as_of_date}', 365)
  GROUP BY m.customer_360_id
),
digital AS (
  SELECT m.customer_360_id,
         COUNT(*) AS digital_events_90d,
         SUM(IF(e.event_type = 'login', 1, 0)) AS logins_90d,
         MAX(e.event_ts) AS last_digital_activity_ts
  FROM silver_digital_events e
  JOIN customer_identity_map m ON m.system = 'digital' AND m.source_customer_id = e.dg_user_id
  WHERE e.event_ts >= DATE_SUB(DATE '${as_of_date}', 90)
  GROUP BY m.customer_360_id
)
SELECT
  b.customer_360_id,
  b.first_name, b.last_name, b.email, b.city, b.state, b.zip,
  b.date_of_birth,
  FLOOR(MONTHS_BETWEEN(DATE '${as_of_date}', b.date_of_birth) / 12) AS age,
  cc.segment, cc.home_branch_id, cc.customer_since,
  ROUND(MONTHS_BETWEEN(DATE '${as_of_date}', COALESCE(cc.customer_since, h.first_product_open_date)) / 12, 1) AS tenure_years,
  s.source_systems, s.source_records,
  b.match_rule = 'unmatched' AS is_unmatched_record,
  COALESCE(h.active_products, 0) AS active_products,
  COALESCE(h.has_checking, 0) AS has_checking, COALESCE(h.has_savings, 0) AS has_savings,
  COALESCE(h.has_cd, 0) AS has_cd, COALESCE(h.has_money_market, 0) AS has_money_market,
  COALESCE(h.has_mortgage, 0) AS has_mortgage, COALESCE(h.has_auto_loan, 0) AS has_auto_loan,
  COALESCE(h.has_heloc, 0) AS has_heloc, COALESCE(h.has_personal_loan, 0) AS has_personal_loan,
  COALESCE(h.has_credit_card, 0) AS has_credit_card,
  COALESCE(h.total_deposit_balance, 0) AS total_deposit_balance,
  COALESCE(h.total_loan_balance, 0) AS total_loan_balance,
  COALESCE(h.total_card_balance, 0) AS total_card_balance,
  COALESCE(h.total_card_limit, 0) AS total_card_limit,
  COALESCE(cs.card_spend_12m, 0) AS card_spend_12m,
  COALESCE(cs.card_txns_12m, 0) AS card_txns_12m,
  ARRAY_CONTAINS(s.source_systems, 'digital') AS is_digitally_enrolled,
  COALESCE(d.digital_events_90d, 0) AS digital_events_90d,
  COALESCE(d.logins_90d, 0) AS logins_90d,
  d.last_digital_activity_ts
FROM base b
JOIN systems s USING (customer_360_id)
LEFT JOIN silver_core_customers cc ON b.system = 'core_banking' AND cc.cb_customer_id = b.source_customer_id
LEFT JOIN holdings h USING (customer_360_id)
LEFT JOIN card_spend cs USING (customer_360_id)
LEFT JOIN digital d USING (customer_360_id);
