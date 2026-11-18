-- Access policies for c360_bank.customer_lifetime_value.
-- Personas come from an entitlement table (Unity Catalog only accepts account-level
-- groups, and the FEVM workspace cannot create them). Masks and row filters look up
-- current_user() in that table. Runs before the pipeline, which attaches these
-- functions to the gold tables. Safe to rerun.

CREATE TABLE IF NOT EXISTS c360_bank.customer_lifetime_value.c360_access_entitlements (
  principal  STRING NOT NULL COMMENT 'User email or service principal application ID, exactly as current_user() returns it',
  persona    STRING NOT NULL COMMENT 'data_owner (full access), business_analyst (all customers, identifiers masked) or relationship_banker (full detail, assigned branches only)',
  branch_ids ARRAY<STRING>   COMMENT 'Branches a relationship banker may see; NULL for other personas',
  updated_at TIMESTAMP       COMMENT 'When this entitlement was last set'
)
COMMENT 'Who may see what in the customer 360 tables. Read by the column mask and row filter functions.';

-- The identity that runs this setup (and owns the pipeline) is the data owner.
MERGE INTO c360_bank.customer_lifetime_value.c360_access_entitlements t
USING (SELECT current_user() AS principal) s
ON t.principal = s.principal
WHEN MATCHED THEN UPDATE SET persona = 'data_owner', branch_ids = NULL, updated_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (principal, persona, branch_ids, updated_at)
  VALUES (s.principal, 'data_owner', NULL, current_timestamp());

CREATE OR REPLACE FUNCTION c360_bank.customer_lifetime_value.c360_current_persona()
RETURNS STRING
COMMENT 'Persona of the calling principal from c360_access_entitlements; NULL if not entitled'
RETURN (SELECT MAX(persona) FROM c360_bank.customer_lifetime_value.c360_access_entitlements
        WHERE principal = current_user());

CREATE OR REPLACE FUNCTION c360_bank.customer_lifetime_value.c360_mask_pii_string(value STRING)
RETURNS STRING
COMMENT 'Column mask: data owners and relationship bankers see the value; everyone else sees ***MASKED***'
RETURN CASE WHEN c360_bank.customer_lifetime_value.c360_current_persona() IN ('data_owner', 'relationship_banker')
            THEN value ELSE '***MASKED***' END;

CREATE OR REPLACE FUNCTION c360_bank.customer_lifetime_value.c360_mask_pii_date(value DATE)
RETURNS DATE
COMMENT 'Column mask: data owners and relationship bankers see the date; everyone else sees NULL (use age instead)'
RETURN CASE WHEN c360_bank.customer_lifetime_value.c360_current_persona() IN ('data_owner', 'relationship_banker')
            THEN value ELSE CAST(NULL AS DATE) END;

CREATE OR REPLACE FUNCTION c360_bank.customer_lifetime_value.c360_branch_filter(home_branch_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: data owners and business analysts see all rows; relationship bankers see only their assigned branches; anyone else sees nothing'
RETURN CASE c360_bank.customer_lifetime_value.c360_current_persona()
  WHEN 'data_owner' THEN TRUE
  WHEN 'business_analyst' THEN TRUE
  WHEN 'relationship_banker' THEN EXISTS (
    SELECT 1 FROM c360_bank.customer_lifetime_value.c360_access_entitlements
    WHERE principal = current_user() AND ARRAY_CONTAINS(branch_ids, home_branch_id))
  ELSE FALSE
END;
