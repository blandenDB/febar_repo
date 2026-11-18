-- Silver products with quality rules (quarantine pattern).
-- Each *_checked view dedupes exact duplicates, types the columns and computes one
-- boolean per rule. Expectations on the view record per-rule pass/fail counts in
-- the pipeline event log. Passing rows go to silver_*; failing rows go to
-- quarantine_records with the names of the rules they broke.

CREATE TEMPORARY VIEW deposit_accounts_checked (
  CONSTRAINT deposit_has_customer_id   EXPECT (ok_has_customer_id),
  CONSTRAINT deposit_known_customer    EXPECT (ok_known_customer),
  CONSTRAINT deposit_balance_not_negative EXPECT (ok_balance_not_negative),
  CONSTRAINT deposit_open_date_not_future EXPECT (ok_open_date_not_future)
) AS
WITH d AS (
  SELECT DISTINCT CAST(account_id AS STRING) AS account_id, CAST(cb_customer_id AS STRING) AS cb_customer_id,
         product_type, CAST(open_date AS DATE) AS open_date, CAST(balance AS DECIMAL(14,2)) AS balance, status
  FROM bronze_deposit_accounts
)
SELECT d.*,
  d.cb_customer_id IS NOT NULL                                  AS ok_has_customer_id,
  c.cb_customer_id IS NOT NULL                                  AS ok_known_customer,
  COALESCE(d.balance >= 0, FALSE)                               AS ok_balance_not_negative,
  COALESCE(d.open_date <= DATE '${as_of_date}', FALSE)          AS ok_open_date_not_future
FROM d LEFT JOIN (SELECT DISTINCT cb_customer_id FROM silver_core_customers) c USING (cb_customer_id);

CREATE TEMPORARY VIEW loans_checked (
  CONSTRAINT loan_has_customer_id      EXPECT (ok_has_customer_id),
  CONSTRAINT loan_known_customer       EXPECT (ok_known_customer),
  CONSTRAINT loan_rate_in_range        EXPECT (ok_rate_in_range),
  CONSTRAINT loan_origination_not_future EXPECT (ok_origination_not_future)
) AS
WITH l AS (
  SELECT DISTINCT CAST(loan_id AS STRING) AS loan_id, CAST(ln_customer_id AS STRING) AS ln_customer_id,
         product_type, CAST(origination_date AS DATE) AS origination_date,
         CAST(original_amount AS DECIMAL(14,2)) AS original_amount,
         CAST(current_balance AS DECIMAL(14,2)) AS current_balance,
         CAST(interest_rate AS DECIMAL(6,3)) AS interest_rate, CAST(term_months AS INT) AS term_months, status
  FROM bronze_loans
)
SELECT l.*,
  l.ln_customer_id IS NOT NULL                                  AS ok_has_customer_id,
  c.ln_customer_id IS NOT NULL                                  AS ok_known_customer,
  COALESCE(l.interest_rate > 0 AND l.interest_rate <= 30, FALSE) AS ok_rate_in_range,
  COALESCE(l.origination_date <= DATE '${as_of_date}', FALSE)   AS ok_origination_not_future
FROM l LEFT JOIN (SELECT DISTINCT CAST(ln_customer_id AS STRING) AS ln_customer_id FROM bronze_loan_customers) c
  USING (ln_customer_id);

CREATE TEMPORARY VIEW card_accounts_checked (
  CONSTRAINT card_has_customer_id      EXPECT (ok_has_customer_id),
  CONSTRAINT card_known_customer       EXPECT (ok_known_customer),
  CONSTRAINT card_has_product_type     EXPECT (ok_has_product_type)
) AS
WITH a AS (
  SELECT DISTINCT CAST(card_id AS STRING) AS card_id, CAST(cc_customer_id AS STRING) AS cc_customer_id,
         product_type, CAST(open_date AS DATE) AS open_date, CAST(credit_limit AS DECIMAL(14,2)) AS credit_limit,
         CAST(current_balance AS DECIMAL(14,2)) AS current_balance, status
  FROM bronze_card_accounts
)
SELECT a.*,
  a.cc_customer_id IS NOT NULL                                  AS ok_has_customer_id,
  c.cc_customer_id IS NOT NULL                                  AS ok_known_customer,
  a.product_type IS NOT NULL                                    AS ok_has_product_type
FROM a LEFT JOIN (SELECT DISTINCT CAST(cc_customer_id AS STRING) AS cc_customer_id FROM bronze_card_customers) c
  USING (cc_customer_id);

CREATE TEMPORARY VIEW digital_events_checked (
  CONSTRAINT event_has_user_id         EXPECT (ok_has_user_id),
  CONSTRAINT event_known_user          EXPECT (ok_known_user)
) AS
WITH e AS (
  SELECT DISTINCT CAST(event_id AS STRING) AS event_id, CAST(dg_user_id AS STRING) AS dg_user_id,
         CAST(event_ts AS TIMESTAMP) AS event_ts, event_type, product, channel
  FROM bronze_digital_events
)
SELECT e.*,
  e.dg_user_id IS NOT NULL                                      AS ok_has_user_id,
  (e.dg_user_id IS NULL OR u.dg_user_id IS NOT NULL)            AS ok_known_user
FROM e LEFT JOIN (SELECT DISTINCT CAST(dg_user_id AS STRING) AS dg_user_id FROM bronze_digital_users) u
  USING (dg_user_id);

-- ---------------------------------------------------------------- clean silver tables
CREATE OR REFRESH MATERIALIZED VIEW silver_deposit_accounts
COMMENT 'Deposit accounts that passed every quality rule'
AS SELECT account_id, cb_customer_id, product_type, open_date, balance, status
FROM deposit_accounts_checked
WHERE ok_has_customer_id AND ok_known_customer AND ok_balance_not_negative AND ok_open_date_not_future;

CREATE OR REFRESH MATERIALIZED VIEW silver_loans
COMMENT 'Loans that passed every quality rule'
AS SELECT loan_id, ln_customer_id, product_type, origination_date, original_amount, current_balance,
          interest_rate, term_months, status
FROM loans_checked
WHERE ok_has_customer_id AND ok_known_customer AND ok_rate_in_range AND ok_origination_not_future;

CREATE OR REFRESH MATERIALIZED VIEW silver_card_accounts
COMMENT 'Card accounts that passed every quality rule'
AS SELECT card_id, cc_customer_id, product_type, open_date, credit_limit, current_balance, status
FROM card_accounts_checked
WHERE ok_has_customer_id AND ok_known_customer AND ok_has_product_type;

CREATE OR REFRESH MATERIALIZED VIEW silver_digital_events
COMMENT 'Digital banking events that passed every quality rule'
AS SELECT event_id, dg_user_id, event_ts, event_type, product, channel
FROM digital_events_checked
WHERE ok_has_user_id AND ok_known_user;

CREATE OR REFRESH MATERIALIZED VIEW silver_card_transactions (
  CONSTRAINT txn_has_card_id EXPECT (card_id IS NOT NULL)
)
COMMENT 'Card transactions, typed, exact duplicates removed'
AS SELECT DISTINCT CAST(txn_id AS STRING) AS txn_id, CAST(card_id AS STRING) AS card_id,
          CAST(txn_ts AS TIMESTAMP) AS txn_ts, CAST(amount AS DECIMAL(12,2)) AS amount, merchant_category
FROM bronze_card_transactions;

-- ---------------------------------------------------------------- quarantine
CREATE OR REFRESH MATERIALIZED VIEW quarantine_records
COMMENT 'Rows that failed one or more quality rules, with the rules they broke and the original record'
AS
SELECT 'deposit_accounts' AS source_table, account_id AS record_id,
  FILTER(ARRAY(
    IF(NOT ok_has_customer_id, 'deposit_has_customer_id', NULL),
    IF(NOT ok_known_customer, 'deposit_known_customer', NULL),
    IF(NOT ok_balance_not_negative, 'deposit_balance_not_negative', NULL),
    IF(NOT ok_open_date_not_future, 'deposit_open_date_not_future', NULL)), x -> x IS NOT NULL) AS failed_rules,
  TO_JSON(STRUCT(account_id, cb_customer_id, product_type, open_date, balance, status)) AS record_json
FROM deposit_accounts_checked
WHERE NOT (ok_has_customer_id AND ok_known_customer AND ok_balance_not_negative AND ok_open_date_not_future)
UNION ALL
SELECT 'loans', loan_id,
  FILTER(ARRAY(
    IF(NOT ok_has_customer_id, 'loan_has_customer_id', NULL),
    IF(NOT ok_known_customer, 'loan_known_customer', NULL),
    IF(NOT ok_rate_in_range, 'loan_rate_in_range', NULL),
    IF(NOT ok_origination_not_future, 'loan_origination_not_future', NULL)), x -> x IS NOT NULL),
  TO_JSON(STRUCT(loan_id, ln_customer_id, product_type, origination_date, original_amount, current_balance,
                 interest_rate, term_months, status))
FROM loans_checked
WHERE NOT (ok_has_customer_id AND ok_known_customer AND ok_rate_in_range AND ok_origination_not_future)
UNION ALL
SELECT 'card_accounts', card_id,
  FILTER(ARRAY(
    IF(NOT ok_has_customer_id, 'card_has_customer_id', NULL),
    IF(NOT ok_known_customer, 'card_known_customer', NULL),
    IF(NOT ok_has_product_type, 'card_has_product_type', NULL)), x -> x IS NOT NULL),
  TO_JSON(STRUCT(card_id, cc_customer_id, product_type, open_date, credit_limit, current_balance, status))
FROM card_accounts_checked
WHERE NOT (ok_has_customer_id AND ok_known_customer AND ok_has_product_type)
UNION ALL
SELECT 'digital_events', event_id,
  FILTER(ARRAY(
    IF(NOT ok_has_user_id, 'event_has_user_id', NULL),
    IF(NOT ok_known_user, 'event_known_user', NULL)), x -> x IS NOT NULL),
  TO_JSON(STRUCT(event_id, dg_user_id, event_ts, event_type, product, channel))
FROM digital_events_checked
WHERE NOT (ok_has_user_id AND ok_known_user);
