-- Identity matching: link every source customer ID to one customer_360_id.
-- Core banking is the anchor (one customer_360_id per core customer). Other systems
-- match to core in tiers; each row records the rule that matched it.
--   Tier 1: exact tax ID token
--   Tier 2: normalized email + date of birth
--   Tier 3: normalized first + last name + date of birth + ZIP
-- Records that match nothing keep their own customer_360_id (flagged 'unmatched').

CREATE OR REFRESH MATERIALIZED VIEW customer_identity_map (
  CONSTRAINT one_360_id_per_source EXPECT (customer_360_id IS NOT NULL)
)
COMMENT 'Maps each source system customer ID to a single customer_360_id, with the rule that matched it'
AS
WITH core AS (
  SELECT * FROM silver_customer_identities WHERE system = 'core_banking'
),
others AS (
  SELECT * FROM silver_customer_identities WHERE system <> 'core_banking'
),
t1 AS (
  SELECT o.system, o.source_customer_id, MIN(c.source_customer_id) AS core_id,
         COUNT(DISTINCT c.source_customer_id) AS candidates
  FROM others o JOIN core c ON o.tax_id_token = c.tax_id_token
  GROUP BY o.system, o.source_customer_id
),
r1 AS (
  SELECT o.* FROM others o LEFT ANTI JOIN t1 USING (system, source_customer_id)
),
t2 AS (
  SELECT o.system, o.source_customer_id, MIN(c.source_customer_id) AS core_id,
         COUNT(DISTINCT c.source_customer_id) AS candidates
  FROM r1 o JOIN core c ON o.email_norm = c.email_norm AND o.date_of_birth = c.date_of_birth
  GROUP BY o.system, o.source_customer_id
),
r2 AS (
  SELECT o.* FROM r1 o LEFT ANTI JOIN t2 USING (system, source_customer_id)
),
t3 AS (
  SELECT o.system, o.source_customer_id, MIN(c.source_customer_id) AS core_id,
         COUNT(DISTINCT c.source_customer_id) AS candidates
  FROM r2 o JOIN core c
    ON o.first_name_norm = c.first_name_norm AND o.last_name_norm = c.last_name_norm
   AND o.date_of_birth = c.date_of_birth AND o.zip = c.zip
  GROUP BY o.system, o.source_customer_id
),
r3 AS (
  SELECT o.* FROM r2 o LEFT ANTI JOIN t3 USING (system, source_customer_id)
)
SELECT system, source_customer_id, CONCAT('C', SUBSTRING(source_customer_id, 3)) AS customer_360_id,
       'anchor' AS match_rule, 1 AS candidates
FROM core
UNION ALL
SELECT system, source_customer_id, CONCAT('C', SUBSTRING(core_id, 3)), 'tax_id_token', candidates FROM t1
UNION ALL
SELECT system, source_customer_id, CONCAT('C', SUBSTRING(core_id, 3)), 'email_dob', candidates FROM t2
UNION ALL
SELECT system, source_customer_id, CONCAT('C', SUBSTRING(core_id, 3)), 'name_dob_zip', candidates FROM t3
UNION ALL
SELECT system, source_customer_id, CONCAT('U', source_customer_id), 'unmatched', 0 FROM r3;
