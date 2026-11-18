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
