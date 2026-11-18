-- title: Row counts per layer
SELECT 'bronze_core_customers' AS table_name, COUNT(*) AS row_count FROM c360_bank.customer_lifetime_value.bronze_core_customers
UNION ALL SELECT 'silver_core_customers', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_core_customers
UNION ALL SELECT 'bronze_deposit_accounts', COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_deposit_accounts
UNION ALL SELECT 'silver_deposit_accounts', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_deposit_accounts
UNION ALL SELECT 'bronze_loans', COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_loans
UNION ALL SELECT 'silver_loans', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_loans
UNION ALL SELECT 'bronze_card_accounts', COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_card_accounts
UNION ALL SELECT 'silver_card_accounts', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_card_accounts
UNION ALL SELECT 'bronze_card_transactions', COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_card_transactions
UNION ALL SELECT 'silver_card_transactions', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_card_transactions
UNION ALL SELECT 'bronze_digital_events', COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_digital_events
UNION ALL SELECT 'silver_digital_events', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_digital_events
UNION ALL SELECT 'silver_customer_identities', COUNT(*) FROM c360_bank.customer_lifetime_value.silver_customer_identities
UNION ALL SELECT 'customer_identity_map', COUNT(*) FROM c360_bank.customer_lifetime_value.customer_identity_map
UNION ALL SELECT 'quarantine_records', COUNT(*) FROM c360_bank.customer_lifetime_value.quarantine_records
UNION ALL SELECT 'gold_product_holdings', COUNT(*) FROM c360_bank.customer_lifetime_value.gold_product_holdings
UNION ALL SELECT 'gold_digital_product_interest', COUNT(*) FROM c360_bank.customer_lifetime_value.gold_digital_product_interest
UNION ALL SELECT 'gold_customer_360', COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360
;
-- title: Exact duplicates removed (bronze rows minus distinct rows)
SELECT 'core_customers' AS source, (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_core_customers)
       - (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.silver_core_customers) AS duplicates_removed, 1000 AS planted
UNION ALL SELECT 'deposit_accounts', (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_deposit_accounts)
       - (SELECT COUNT(DISTINCT account_id) FROM c360_bank.customer_lifetime_value.bronze_deposit_accounts), 1670
UNION ALL SELECT 'card_accounts', (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.bronze_card_accounts)
       - (SELECT COUNT(DISTINCT card_id) FROM c360_bank.customer_lifetime_value.bronze_card_accounts), 443
;
-- title: Quarantined rows per rule (a row can break more than one rule)
SELECT source_table, rule, COUNT(*) AS rows_failed
FROM c360_bank.customer_lifetime_value.quarantine_records LATERAL VIEW EXPLODE(failed_rules) r AS rule
GROUP BY source_table, rule ORDER BY source_table, rule
;
-- title: Identity matching: source records per system and match rule
SELECT system, match_rule, COUNT(*) AS records, SUM(IF(candidates > 1, 1, 0)) AS ambiguous
FROM c360_bank.customer_lifetime_value.customer_identity_map
GROUP BY system, match_rule ORDER BY system, match_rule
;
-- title: Matching accuracy against generator ground truth (non-core systems)
WITH truth AS (
  SELECT system, source_customer_id, person_id
  FROM read_files('/Volumes/c360_bank/customer_lifetime_value/ground_truth/identity_map', format => 'csv', header => true)
),
core_truth AS (SELECT source_customer_id AS core_id, person_id FROM truth WHERE system = 'core_banking'),
expected AS (
  SELECT t.system, t.source_customer_id, CONCAT('C', SUBSTRING(c.core_id, 3)) AS true_360_id
  FROM truth t JOIN core_truth c USING (person_id) WHERE t.system <> 'core_banking'
)
SELECT e.system,
  COUNT(*) AS records,
  SUM(IF(m.match_rule <> 'unmatched', 1, 0)) AS matched,
  SUM(IF(m.customer_360_id = e.true_360_id, 1, 0)) AS matched_correctly,
  ROUND(SUM(IF(m.customer_360_id = e.true_360_id, 1, 0)) / NULLIF(SUM(IF(m.match_rule <> 'unmatched', 1, 0)), 0), 4) AS precision,
  ROUND(SUM(IF(m.customer_360_id = e.true_360_id, 1, 0)) / COUNT(*), 4) AS recall
FROM expected e JOIN c360_bank.customer_lifetime_value.customer_identity_map m USING (system, source_customer_id)
GROUP BY e.system ORDER BY e.system
;
-- title: Customer 360 summary
SELECT COUNT(*) AS customers,
  SUM(IF(is_unmatched_record, 1, 0)) AS unmatched_records,
  ROUND(AVG(active_products), 2) AS avg_active_products,
  SUM(IF(SIZE(source_systems) >= 3, 1, 0)) AS customers_in_3plus_systems,
  ROUND(SUM(total_deposit_balance) / 1e6, 1) AS deposits_musd,
  ROUND(SUM(total_loan_balance) / 1e6, 1) AS loans_musd
FROM c360_bank.customer_lifetime_value.gold_customer_360
;
-- title: Sample customer 360 rows (synthetic)
SELECT customer_360_id, segment, age, tenure_years, source_systems, active_products,
       has_checking, has_savings, has_mortgage, has_credit_card, total_deposit_balance, card_spend_12m, digital_events_90d
FROM c360_bank.customer_lifetime_value.gold_customer_360
WHERE SIZE(source_systems) = 4 ORDER BY customer_360_id LIMIT 5

;
-- title: Expectation results from the pipeline event log (latest update)
WITH ev AS (
  SELECT origin.update_id, timestamp, origin.flow_name,
         from_json(details:flow_progress:data_quality:expectations,
                   'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>') AS exps
  FROM event_log(TABLE(c360_bank.customer_lifetime_value.gold_customer_360))
  WHERE event_type = 'flow_progress' AND details:flow_progress:data_quality:expectations IS NOT NULL
),
latest AS (
  SELECT update_id FROM ev ORDER BY timestamp DESC LIMIT 1
)
SELECT e.flow_name AS flow, x.name AS expectation, SUM(x.passed_records) AS passed, SUM(x.failed_records) AS failed
FROM ev e JOIN latest USING (update_id) LATERAL VIEW EXPLODE(exps) t AS x
GROUP BY e.flow_name, x.name ORDER BY flow, expectation
