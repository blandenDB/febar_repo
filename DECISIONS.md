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
