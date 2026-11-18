-- Governance proof: the same queries run as each persona. The caller's entitlement is
-- switched between personas, then restored to data_owner at the end.
-- title: Masks and row filters attached to the gold tables
SELECT table_name, column_name, mask_name AS policy FROM c360_bank.information_schema.column_masks
WHERE table_schema = 'customer_lifetime_value'
UNION ALL
SELECT table_name, filter_column_names, filter_name FROM (
  SELECT table_name, CONCAT_WS(',', target_columns) AS filter_column_names, filter_name
  FROM c360_bank.information_schema.row_filters WHERE table_schema = 'customer_lifetime_value')
ORDER BY table_name, column_name;
-- title: [data_owner] persona, rows visible, sample identifiers
SELECT c360_bank.customer_lifetime_value.c360_current_persona() AS persona,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS customers_visible,
       (SELECT COUNT(DISTINCT home_branch_id) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS branches_visible,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_product_holdings) AS holdings_visible;
-- title: [data_owner] sample rows
SELECT customer_360_id, first_name, last_name, email, date_of_birth, age, home_branch_id, active_products
FROM c360_bank.customer_lifetime_value.gold_customer_360 ORDER BY customer_360_id LIMIT 3;
-- title: switch caller to business_analyst
UPDATE c360_bank.customer_lifetime_value.c360_access_entitlements
SET persona = 'business_analyst', branch_ids = NULL, updated_at = current_timestamp()
WHERE principal = current_user();
-- title: [business_analyst] persona, rows visible
SELECT c360_bank.customer_lifetime_value.c360_current_persona() AS persona,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS customers_visible,
       (SELECT COUNT(DISTINCT home_branch_id) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS branches_visible,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_product_holdings) AS holdings_visible;
-- title: [business_analyst] same sample rows: identifiers masked, age still available
SELECT customer_360_id, first_name, last_name, email, date_of_birth, age, home_branch_id, active_products
FROM c360_bank.customer_lifetime_value.gold_customer_360 ORDER BY customer_360_id LIMIT 3;
-- title: switch caller to relationship_banker for branches BR001 and BR002
UPDATE c360_bank.customer_lifetime_value.c360_access_entitlements
SET persona = 'relationship_banker', branch_ids = ARRAY('BR001', 'BR002'), updated_at = current_timestamp()
WHERE principal = current_user();
-- title: [relationship_banker] persona, rows visible (assigned branches only)
SELECT c360_bank.customer_lifetime_value.c360_current_persona() AS persona,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS customers_visible,
       (SELECT CONCAT_WS(',', ARRAY_SORT(COLLECT_SET(home_branch_id))) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS branches_visible,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_product_holdings) AS holdings_visible;
-- title: [relationship_banker] sample rows: full identifiers, own branches only
SELECT customer_360_id, first_name, last_name, email, date_of_birth, age, home_branch_id, active_products
FROM c360_bank.customer_lifetime_value.gold_customer_360 ORDER BY customer_360_id LIMIT 3;
-- title: switch caller to a principal with no entitlement
UPDATE c360_bank.customer_lifetime_value.c360_access_entitlements
SET persona = 'none', branch_ids = NULL, updated_at = current_timestamp()
WHERE principal = current_user();
-- title: [no entitlement] rows visible
SELECT c360_bank.customer_lifetime_value.c360_current_persona() AS persona,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS customers_visible;
-- title: restore caller to data_owner
UPDATE c360_bank.customer_lifetime_value.c360_access_entitlements
SET persona = 'data_owner', branch_ids = NULL, updated_at = current_timestamp()
WHERE principal = current_user();
-- title: [restored] persona and rows visible
SELECT c360_bank.customer_lifetime_value.c360_current_persona() AS persona,
       (SELECT COUNT(*) FROM c360_bank.customer_lifetime_value.gold_customer_360) AS customers_visible;
-- title: Data owner check: branch split of the full table (expected banker count = BR001 + BR002)
SELECT home_branch_id, COUNT(*) AS customers FROM c360_bank.customer_lifetime_value.gold_customer_360
WHERE home_branch_id IN ('BR001', 'BR002') GROUP BY home_branch_id ORDER BY home_branch_id
;
-- title: Tags on gold_customer_360 columns
SELECT table_name, column_name, tag_name, tag_value FROM c360_bank.information_schema.column_tags
WHERE schema_name = 'customer_lifetime_value' ORDER BY table_name, column_name;
-- title: Table tags
SELECT table_name, tag_name, tag_value FROM c360_bank.information_schema.table_tags
WHERE schema_name = 'customer_lifetime_value' ORDER BY table_name
