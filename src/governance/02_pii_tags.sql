-- PII tags on the gold customer 360 columns that carry direct identifiers.
-- Runs after the pipeline. Safe to rerun.
-- The shared FEVM metastore governs the keys `pii` (allowed: ssn, address) and
-- `data_classification` (allowed: u-nnpi, cui, pii), so column detail uses our own
-- prefixed key `c360_pii_type`.
ALTER MATERIALIZED VIEW c360_bank.customer_lifetime_value.gold_customer_360 SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW c360_bank.customer_lifetime_value.gold_customer_360 ALTER COLUMN first_name SET TAGS ('c360_pii_type' = 'name');
ALTER MATERIALIZED VIEW c360_bank.customer_lifetime_value.gold_customer_360 ALTER COLUMN last_name SET TAGS ('c360_pii_type' = 'name');
ALTER MATERIALIZED VIEW c360_bank.customer_lifetime_value.gold_customer_360 ALTER COLUMN email SET TAGS ('c360_pii_type' = 'email');
ALTER MATERIALIZED VIEW c360_bank.customer_lifetime_value.gold_customer_360 ALTER COLUMN date_of_birth SET TAGS ('c360_pii_type' = 'date_of_birth');
ALTER TABLE c360_bank.customer_lifetime_value.c360_access_entitlements SET TAGS ('c360_sensitivity' = 'access_control');
