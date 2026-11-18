-- Lakebase (Postgres) setup for the relationship banker app. Safe to rerun.
--
-- Identity: the app sets the signed-in banker for each transaction with
--   SELECT set_config('app.banker', '<email from the Databricks Apps forwarded header>', true)
-- Synced tables (schema customer_lifetime_value, pg_*) are owned by the sync, so access
-- to them goes through security_barrier views that keep only the banker's branches.
-- banker_feedback is owned by us and uses Postgres row-level security.
-- The app's role is granted only the app schema (src/serve/postgres_setup.py adds it).

CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE VIEW app.my_branches WITH (security_barrier = true) AS
SELECT jsonb_array_elements_text(a.branch_ids) AS branch_id
FROM customer_lifetime_value.pg_banker_assignments a
WHERE a.banker_principal = current_setting('app.banker', true);

CREATE OR REPLACE VIEW app.customers WITH (security_barrier = true) AS
SELECT c.* FROM customer_lifetime_value.pg_customer_360 c
WHERE c.home_branch_id IN (SELECT branch_id FROM app.my_branches);

CREATE OR REPLACE VIEW app.holdings WITH (security_barrier = true) AS
SELECT h.* FROM customer_lifetime_value.pg_product_holdings h
WHERE h.home_branch_id IN (SELECT branch_id FROM app.my_branches);

CREATE OR REPLACE VIEW app.recommendations WITH (security_barrier = true) AS
SELECT r.* FROM customer_lifetime_value.pg_recommendations r
WHERE r.home_branch_id IN (SELECT branch_id FROM app.my_branches);

CREATE TABLE IF NOT EXISTS app.banker_feedback (
  feedback_id      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_360_id  text        NOT NULL,
  home_branch_id   text        NOT NULL,
  product          text        NOT NULL,
  action           text        NOT NULL CHECK (action IN ('accepted', 'declined', 'follow_up', 'not_interested_now')),
  note             text        CHECK (char_length(note) <= 1000),
  banker_principal text        NOT NULL DEFAULT current_setting('app.banker', true),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS banker_feedback_customer_idx ON app.banker_feedback (customer_360_id, created_at DESC);

ALTER TABLE app.banker_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS feedback_read_own_branches ON app.banker_feedback;
CREATE POLICY feedback_read_own_branches ON app.banker_feedback FOR SELECT
  USING (home_branch_id IN (SELECT branch_id FROM app.my_branches));

DROP POLICY IF EXISTS feedback_insert_own_branches ON app.banker_feedback;
CREATE POLICY feedback_insert_own_branches ON app.banker_feedback FOR INSERT
  WITH CHECK (home_branch_id IN (SELECT branch_id FROM app.my_branches)
              AND banker_principal = current_setting('app.banker', true));
