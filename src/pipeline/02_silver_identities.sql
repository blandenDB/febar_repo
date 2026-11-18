-- Silver identities: one deduplicated, typed, normalized identity record per
-- source customer ID, across all four systems. Exact duplicate rows collapse here.

CREATE OR REFRESH MATERIALIZED VIEW silver_core_customers
COMMENT 'Core banking customers, exact duplicates removed, typed'
AS SELECT DISTINCT
  CAST(cb_customer_id AS STRING)  AS cb_customer_id,
  CAST(tax_id_token AS STRING)    AS tax_id_token,
  first_name, last_name,
  CAST(date_of_birth AS DATE)     AS date_of_birth,
  email, CAST(phone AS STRING) AS phone, address_line, city, state,
  LPAD(CAST(zip AS STRING), 5, '0') AS zip,
  segment, home_branch_id,
  CAST(customer_since AS DATE)    AS customer_since
FROM bronze_core_customers;

CREATE OR REFRESH MATERIALIZED VIEW silver_customer_identities (
  CONSTRAINT has_source_customer_id EXPECT (source_customer_id IS NOT NULL),
  CONSTRAINT has_date_of_birth EXPECT (date_of_birth IS NOT NULL)
)
COMMENT 'Identity records from all four source systems with normalized match keys'
AS
WITH src AS (
  SELECT DISTINCT 'core_banking' AS system, CAST(cb_customer_id AS STRING) AS source_customer_id,
         CAST(tax_id_token AS STRING) AS tax_id_token, first_name, last_name,
         CAST(date_of_birth AS DATE) AS date_of_birth, email, CAST(phone AS STRING) AS phone,
         address_line, city, state, CAST(zip AS STRING) AS zip
  FROM bronze_core_customers
  UNION ALL
  SELECT DISTINCT 'loans', CAST(ln_customer_id AS STRING), CAST(tax_id_token AS STRING), first_name,
         last_name, CAST(date_of_birth AS DATE), email, CAST(phone AS STRING), address_line, city,
         state, CAST(zip AS STRING)
  FROM bronze_loan_customers
  UNION ALL
  SELECT DISTINCT 'cards', CAST(cc_customer_id AS STRING), CAST(tax_id_token AS STRING), first_name,
         last_name, CAST(date_of_birth AS DATE), email, CAST(phone AS STRING), address_line, city,
         state, CAST(zip AS STRING)
  FROM bronze_card_customers
  UNION ALL
  SELECT DISTINCT 'digital', CAST(dg_user_id AS STRING), CAST(NULL AS STRING), first_name,
         last_name, CAST(date_of_birth AS DATE), email, CAST(phone AS STRING), address_line, city,
         state, CAST(zip AS STRING)
  FROM bronze_digital_users
)
SELECT
  system, source_customer_id, tax_id_token, first_name, last_name, date_of_birth, email, phone,
  address_line, city, state, LPAD(zip, 5, '0') AS zip,
  LOWER(TRIM(first_name))                              AS first_name_norm,
  LOWER(TRIM(last_name))                               AS last_name_norm,
  LOWER(TRIM(email))                                   AS email_norm,
  RIGHT(REGEXP_REPLACE(phone, '[^0-9]', ''), 10)       AS phone_norm
FROM src;
