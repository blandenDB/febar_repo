-- title: Raw row counts read back from the volume with read_files()
SELECT 'core_banking/customers' AS source, COUNT(*) AS row_count FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/core_banking/customers', format => 'csv', header => true)
UNION ALL SELECT 'core_banking/deposit_accounts', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/core_banking/deposit_accounts', format => 'csv', header => true)
UNION ALL SELECT 'loans/customers', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/loans/customers', format => 'csv', header => true)
UNION ALL SELECT 'loans/loans', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/loans/loans', format => 'csv', header => true)
UNION ALL SELECT 'cards/customers', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/cards/customers', format => 'json')
UNION ALL SELECT 'cards/card_accounts', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/cards/card_accounts', format => 'json')
UNION ALL SELECT 'cards/card_transactions', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/cards/card_transactions', format => 'json')
UNION ALL SELECT 'digital/users', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/digital/users', format => 'json')
UNION ALL SELECT 'digital/events', COUNT(*) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/digital/events', format => 'json')
;
-- title: Sample raw identity rows for one synthetic person across systems (shows planted identity drift)
WITH t AS (SELECT * FROM read_files('/Volumes/c360_bank/customer_lifetime_value/ground_truth/identity_map', format => 'csv', header => true)),
p AS (SELECT person_id FROM t GROUP BY person_id HAVING COUNT(DISTINCT system) = 4 ORDER BY person_id LIMIT 1)
SELECT t.system, t.source_customer_id, i.first_name, i.last_name, i.date_of_birth, i.email, i.phone, i.zip
FROM t JOIN p USING (person_id)
JOIN (
  SELECT 'core_banking' AS system, cb_customer_id AS id, first_name, last_name, date_of_birth, email, phone, CAST(zip AS STRING) AS zip FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/core_banking/customers', format => 'csv', header => true)
  UNION ALL SELECT 'loans', ln_customer_id, first_name, last_name, date_of_birth, email, phone, CAST(zip AS STRING) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/loans/customers', format => 'csv', header => true)
  UNION ALL SELECT 'cards', cc_customer_id, first_name, last_name, date_of_birth, email, CAST(phone AS STRING), CAST(zip AS STRING) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/cards/customers', format => 'json')
  UNION ALL SELECT 'digital', dg_user_id, first_name, last_name, date_of_birth, email, CAST(phone AS STRING), CAST(zip AS STRING) FROM read_files('/Volumes/c360_bank/customer_lifetime_value/raw/digital/users', format => 'json')
) i ON i.system = t.system AND i.id = t.source_customer_id
ORDER BY t.system
