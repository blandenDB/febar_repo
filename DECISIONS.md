# Decisions

[YOUR WORDS] Rewrite each entry in your own words.

## 2026-11-18: Workspace

- **Decision:** a new FEVM workspace (AWS Stable Serverless, us-west-2), not an existing one.
- **Options considered:** a new FEVM workspace; an FEVM workspace owned by someone else; the shared tech-summit sandbox; the old banking demo workspace (likely expired).
- **Why:** [YOUR WORDS]

## 2026-11-18: Unity Catalog names

- **Decision:** catalog `c360_bank`, schema `customer_lifetime_value`.
- **Options considered:** for the catalog, (A) an FEVM Standalone Catalog named `c360_bank`, (B) the catalog FEVM creates with the workspace, (C) a temporary metastore grant to create the catalog myself. For the schema, one schema versus several schemas (one per pipeline layer).
- **Why:** [YOUR WORDS]

## 2026-11-18: Use case story

- **Decision:** products to cross-sell. Use the full customer 360 view (which bank products each customer holds and how they use them) to find the next product most likely to raise customer lifetime value.
- **Options considered:** products to cross-sell; spotting customers likely to leave; an advisor's next best action.
- **Why:** [YOUR WORDS]

## 2026-11-18: Personas

- **Decision:** Business Analysts use the Genie agent (ask questions about portfolio, product penetration and CLV in plain language). Relationship Bankers use the Databricks App (look up a customer, see the 360 view and the recommended next product).
- **Options considered:** [YOUR WORDS] (list any alternatives you weighed)
- **Why:** [YOUR WORDS]

## 2026-11-18: Raw synthetic data sources

- **Decision:** four core source systems, each with its own customer ID: core banking (customers and deposit accounts), loans (mortgage, auto, HELOC), cards, digital banking events. Landed as raw files in a UC volume under `c360_bank.customer_lifetime_value`. Proposed size about 50,000 customers, 150,000 product accounts, 2 million transactions/events, fixed random seed.
- **Options considered:** (A) four core systems; (B) two systems (customers plus holdings, transactions); (C) five systems adding CRM interactions with banker notes.
- **Why:** [YOUR WORDS]

## 2026-11-18: Planted data issues

- **Decision:** focused bundle, each at 1 to 3% of rows: (1) the same customer under different IDs across systems with small differences; (2) duplicate rows in core banking and cards; (3) orphan loan and card accounts; (4) bad values (negative deposit balances, future dates, out-of-range rates); (6) missing key fields (null customer IDs on events, null product type).
- **Options considered:** (A) focused; (B) full, adding mixed formats and late/changed records; (C) minimal, only issues 1 to 3.
- **Why:** [YOUR WORDS]

## 2026-11-18: Quality rule handling

- **Decision:** quarantine. Rows that pass the rules flow to the clean (silver) tables; rows that fail go to `quarantine_*` tables tagged with the rules they broke. Per-rule counts come from the pipeline event log as evidence.
- **Options considered:** (A) quarantine; (B) drop with expectations; (C) mixed fail/quarantine/warn.
- **Why:** [YOUR WORDS]
- **Duplicates:** exact duplicate rows are deduplicated (one copy kept, count removed reported), not quarantined. Option considered: quarantine them like other failures. Why: [YOUR WORDS]

## 2026-11-18: Customer matching

- **Decision:** rules-based matching in SQL. Normalize identifying fields, then match in tiers: (1) exact synthetic tax-ID token, (2) email plus date of birth, (3) normalized name plus date of birth plus ZIP. Each match records its rule. Precision and recall are measured against generator ground truth.
- **Options considered:** (A) rules-based SQL; (B) rules plus fuzzy name similarity; (C) ML pair matching.
- **Why:** [YOUR WORDS]

## 2026-11-18: Access rules

- **Decision:** two groups, `c360_business_analysts` (Genie) and `c360_relationship_bankers` (app). Analysts see all customers with direct identifiers masked (name, email, date of birth); bankers see full detail only for customers in their assigned branches. Quarantine and ground truth are not granted to either group. Add table/column comments and PII tags.
- **Options considered:** (A) groups plus column masks plus row filter; (B) tag-based ABAC policies; (C) grants only.
- **Why:** [YOUR WORDS]

## 2026-11-18: How personas are identified (access rules follow-up)

- **Decision:** an entitlement table `c360_access_entitlements` maps each principal (user or service principal) to a persona (`data_owner`, `business_analyst`, `relationship_banker`) and, for bankers, the branches they serve. UC column masks and row filters look up `current_user()` in it. The app's service principal will be the banker principal.
- **Options considered:** entitlement table; ask an account admin for account-level groups; dynamic views only.
- **Context:** FEVM workspace admins can only create workspace-local groups, which Unity Catalog rejects (`PRINCIPAL_DOES_NOT_EXIST`).
- **Why:** [YOUR WORDS]

## 2026-11-18: AI approach

- **Decision:** per-product propensity models (trained on customers who opened the product in the last 120 days; MLflow tracked, registered in UC) plus a foundation model that writes a short, fact-grounded banker explanation for the top recommendation.
- **Options considered:** (A) propensity models only; (B) propensity models plus GenAI explanation; (C) GenAI only.
- **Why:** [YOUR WORDS]

## 2026-11-18: CLV method

- **Decision:** CLV = sum over held products of annual margin x expected remaining years, discounted. Cross-sell value = added product margin x expected lifetime x propensity.
- **Options considered:** (A) margin x expected lifetime; (B) current annual revenue only; (C) ML-predicted CLV.
- **Why:** [YOUR WORDS]
- **Assumptions [YOUR WORDS]:** accepted as an illustrative starting point (not sourced benchmarks; replace with your own). Annual margin: checking 2.0% of balance + $60/yr fees; savings 1.5%; CD 1.0%; money market 1.25%; mortgage 1.0%; auto loan 2.0%; HELOC 2.5%; personal loan 4.0%; credit card 1.5% of annual spend + 10% of balance. Annual retention: 85% (1 product), 90% (2), 94% (3 or more). Horizon 10 years, discount rate 8%. New-product balance = median of current holders in the same segment. Stored in config tables `clv_product_assumptions` and `clv_parameters`.

## 2026-11-18: Explanation model

- **Decision:** `databricks-claude-haiku-5-5` writes the banker-facing explanation.
- **Options considered:** Claude Haiku 5.5; Claude Sonnet 5.5; GPT-5.4 mini.
- **Why:** [YOUR WORDS]

## 2026-11-18: Recommendation ranking

- **Decision:** rank each customer's eligible products by expected CLV uplift (propensity x CLV uplift if adopted), where eligible means propensity is at least 3x that product's base rate. Customers with no eligible product get "no strong recommendation".
- **Options considered:** uplift with a propensity floor; propensity only; pure expected value (made mortgage the #1 product for 25,144 customers at a median propensity of 0.09%).
- **Why:** [YOUR WORDS]

## 2026-11-18: Generator realism fix

- **Decision:** products are opened at onboarding (60%) or acquired later at a constant rate (mean wait about 6 years), instead of spread evenly over tenure.
- **Options considered:** fix the generator; keep it and explain the onboarding effect.
- **Context:** before the fix, 53% of customers under 6 months' tenure opened a product in any 60-day window (2% for 5-year customers), so tenure drove a 0.94 AUC.
- **Why:** [YOUR WORDS]

## 2026-11-18: Synthetic cross-sell rate

- **Decision:** raise the synthetic bank's cross-sell rate so about 10% of customers open a new product per year (it was about 4%).
- **Options considered:** raise to about 10% a year; keep the data and report small per-product counts with caveats.
- **Context:** model v2 had only 1,453 positives; some products had 9 to 25 test positives.
- **Why:** [YOUR WORDS]

## 2026-11-18: Lakebase operational serving

- **Decision:** sync the banker-facing UC tables (customer 360, holdings, recommendations, explanations, entitlements) to Lakebase; the app writes banker actions to a `banker_feedback` table in Lakebase; Postgres row-level security limits each banker to their branches using the synced entitlements; feedback flows back to UC for Genie.
- **Options considered:** (A) synced reads + feedback write-back + Postgres row-level security; (B) synced reads only with filtering in app code; (C) no Lakebase, app reads UC through the SQL warehouse.
- **Context:** syncs run as the data owner, so UC row filters do not carry into Postgres; access must be enforced again there.
- **Why:** [YOUR WORDS]

## 2026-11-18: Genie space

- **Decision:** analyst portfolio space over gold_customer_360, gold_product_holdings, gold_customer_clv, gold_cross_sell_recommendations and banker_feedback, with instructions and sample questions.
- **Options considered:** (A) analyst portfolio space; (B) minimal (customer 360 and recommendations); (C) A plus quarantine_records.
- **Why:** [YOUR WORDS]

## 2026-11-18: App stack

- **Decision:** Streamlit Databricks App reading the Lakebase `app` views and writing banker_feedback. Screens: My book, Customer 360 with recommendations and explanation, Record outcome.
- **Options considered:** (A) Streamlit; (B) FastAPI plus React; (C) Dash.
- **Why:** [YOUR WORDS]

## 2026-11-19: Use case framing

- **Decision:** USE_CASE.md approved. Prototype scale stays at 50,000 synthetic customers and 25 branches (a stated sample of a 1.3M-customer, 522-branch bank). CRM is out of the system scope (4 systems). Win measure: cross-sell campaign response rate of 4% or more at 6 months, from 1.5% today.
- **Options considered:** raise the synthetic scale; add a CRM source; keep assumed baselines.
- **Why:** [YOUR WORDS]

## 2026-11-19: Build plan decisions [REWRITE IN YOUR WORDS]

Reconfirmed from earlier entries (unchanged): ingestion with Auto Loader from files in a UC volume (alternative: Lakeflow Connect or JDBC from SQL Server); four systems merged (alternative: one source); quarantine plus dedupe with warn-only identity checks and no failing rule (alternative: fail the update on a null core customer ID); personas data owner, business analyst and relationship banker (alternative: add a CDO auditor persona); Lakebase synced tables from gold plus a separate banker_feedback table (alternative: one job-upserted table that keeps human edits); propensity model plus ai_query explanations (alternative: only one); Streamlit app with My book, Customer 360 and Record outcome (alternative: FastAPI and React).

### Non-admin identity for the access test

- **Decision:** a dedicated service principal `c360-access-tester`, entitled first as business_analyst and then as relationship_banker, runs the access queries with a short-lived OAuth secret held only in memory and deleted after the test.
- **Options considered:** dedicated test service principal; the app's service principal.
- **Why:** [REWRITE IN YOUR WORDS]

### How AI output is evaluated

- **Decision:** the rule checks on every explanation, plus an LLM judge (MLflow GenAI evaluation) on 200 sampled explanations for groundedness, relevance and an opening question. Bars in EVAL_PROTOCOL.md.
- **Options considered:** rule checks plus LLM judge; rule checks only.
- **Why:** [REWRITE IN YOUR WORDS]

### Evaluation protocol

- **Decision:** EVAL_PROTOCOL.md (committed 2026-11-19 before the test ran): simple baseline = recent product page views; out-of-time test on the newest 60-day window; main measure = top-decile lift; claim only if lift >= 2.7x and >= 1.2x the baseline's lift.
- **Options considered:** report only the existing out-of-customer results; a protocol with a weaker bar (beat the base rate only).
- **Why:** [REWRITE IN YOUR WORDS]

### Trigger

- **Decision:** one end-to-end job triggered by file arrival on the raw volume, so it runs when the end-of-day files land.
- **Options considered:** file arrival; daily schedule after the batch window; manual runs.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Explanations missed the groundedness bar [REWRITE IN YOUR WORDS]

- **Decision:** tighten the explanation prompt (no inferences about creditworthiness, income, capacity, needs or life events; say less when facts are thin), regenerate, and re-run the same judge on the same sample. Run 1 stays on record; the change is a dated note in EVAL_PROTOCOL.md.
- **Options considered:** tighten and re-run; report the miss and label explanations as drafts; tighten and add an app warning.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Explanations, second miss [REWRITE IN YOUR WORDS]

- **Decision:** give the explanation model richer, true facts (balances, card spend, digital logins, product count, a similar-customers rate) and keep the strict prompt; re-run the same judge on the same sample.
- **Options considered:** richer facts and run 3; report runs 1 and 2 as misses; explain only recommendations with a browsing signal.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Serving layer in its own schema [REWRITE IN YOUR WORDS]

- **Decision:** move the owner-only serving copies (serving_*), the Lakebase synced tables (pg_*) and their sync event logs to c360_bank.serving. The business schema keeps pipeline, gold, governance and ML tables; pipeline event logs go to c360_bank.pipeline_ops.
- **Options considered:** move the serving layer; leave 4 sync event logs in the business schema and document it.
- **Context:** Lakebase sync pipelines always write their event logs into the synced table's schema, whatever storage schema is set.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Trigger changed to a daily schedule [REWRITE IN YOUR WORDS]

- **Decision:** run c360_end_to_end daily at 06:00 US Central, after the end-of-day batch window. This replaces the file arrival trigger chosen earlier today.
- **Options considered:** one more file-arrival attempt on a dedicated landing volume, then a schedule; a schedule now; keep investigating the file-arrival trigger.
- **Context:** the file arrival trigger on /Volumes/c360_bank/customer_lifetime_value/raw/_landing/ was configured and unpaused, but the platform never evaluated it (trigger_state stayed empty) and two drop markers written after it went live started no run.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Business deck and role-play [REWRITE IN YOUR WORDS]

- **Decision:** problem-led storyline (about 10 slides) for the EVP Data & Analytics and the CDO; Google Slides on the Databricks template, exported to PDF and committed; role-play prep with likely questions and evidence, hard objections, and a practice script with a demo path.
- **Options considered:** storyline problem-led, value-led or demo-led; format Markdown plus PDF, Google Slides plus PDF, or Markdown only.
- **Why:** [REWRITE IN YOUR WORDS]

## 2026-11-19: Do not recommend products the customer closed [REWRITE IN YOUR WORDS]

- **Decision:** exclude any product the customer previously held and closed from recommendations, in training and scoring alike.
- **Options considered:** exclude products closed in the last 12 months (not possible: no closure date in the data); exclude any previously closed product; leave it.
- **Context:** 76 recommendations (65 of them #1) were for a product the customer had closed, including the customer on deck slide 6.
- **Why:** [REWRITE IN YOUR WORDS]
