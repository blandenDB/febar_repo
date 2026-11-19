# Build plan: customer 360 and next best product

Implements `USE_CASE.md` under the rules in `FEBAR_CONTEXT.md`. Everything lives in `c360_bank.customer_lifetime_value` and is deployed by the bundle in this repo. Status column: **built** = running in the workspace with evidence; **to do** = decided, not yet built.

## 1. Data flow

```
 SOURCE SYSTEMS (synthetic, end-of-day files)        job c360_generate_raw_data
   core banking | loans | cards | digital  ───────►  /Volumes/.../raw/<system>/<table>/   + raw/_landing/ marker
                                                      /Volumes/.../ground_truth/ (never read by the pipeline)
                                   │  file arrival on raw/_landing/ triggers job c360_end_to_end
                                   ▼
 [1 LAKEFLOW PIPELINE c360_lakeflow_pipeline]  (SQL, serverless)
   bronze_* (9 streaming tables, Auto Loader, + _source_file, _ingested_at)
     └► silver_core_customers, silver_customer_identities          (dedupe, type, normalize match keys)
     └► *_checked views ──► silver_deposit_accounts | silver_loans | silver_card_accounts | silver_digital_events
                        └─► quarantine_records                     (rows that broke a rule + rule names)
     └► silver_card_transactions
     └► customer_identity_map                                      (tiered matching to customer_360_id)
     └► customer_home_branch
     └► gold_product_holdings | gold_digital_product_interest | gold_customer_360
            (column masks + branch row filter attached in the definitions)
                                   ▼
 [2 UNITY CATALOG]  c360_access_entitlements ─► c360_current_persona(), c360_mask_pii_*, c360_branch_filter
                    PII tags, comments, lineage on every table above and below
                                   ▼
 [3 ML + GenAI]  clv_product_assumptions, clv_parameters ─┐
                 gold_* + silver_digital_events ──────────┴► train_and_score ─► model c360_bank...cross_sell_propensity@champion
                                                                            ─► gold_customer_clv
                                                                            ─► gold_cross_sell_recommendations
                 gold_cross_sell_recommendations ─► ai_query(claude-haiku-5-5) ─► gold_recommendation_explanations
                                   ▼
 [4 LAKEBASE]  serving_customer_360 | serving_product_holdings | serving_recommendations | serving_banker_assignments
               ──synced (SNAPSHOT)──► Postgres customer_lifetime_value.pg_*  ──► app.* security_barrier views
               app.banker_feedback (written by the app, Postgres RLS) ──job c360_feedback_sync──► UC banker_feedback
                                   ▼                                              │
 [6 APP c360-banker]  reads app.* views, writes app.banker_feedback ◄─────────────┘
                                                                                  ▼
 [5 GENIE]  gold_customer_360, gold_product_holdings, gold_customer_clv, gold_cross_sell_recommendations, banker_feedback
```

Each stage reads the previous stage's output: remove any one and the next one has no input.

## 2. Stages

| Stage | What it does for the CDO | Inputs | Outputs | Features | Verified by | Evidence | Status |
|---|---|---|---|---|---|---|---|
| Lakeflow | One tested pipeline replaces per-product extracts; bad rows are kept and explained, people are matched across systems | raw volume files | bronze_*, silver_*, quarantine_records, customer_identity_map, gold_* | Auto Loader, Lakeflow Spark Declarative Pipelines (SQL), expectations, serverless | Planted counts from the generator manifest = duplicates removed and rows quarantined per rule; matching precision and recall against ground truth; rerun adds no rows | `02_pipeline.txt` | built |
| Unity Catalog | One access policy for every consumer: analysts see all customers with PII masked, bankers see only their branches | gold_*, c360_access_entitlements | masks, row filter, tags, comments | column masks, row filters, governed tags, comments, lineage | Same queries as each persona; **non-admin service principal** `c360-access-tester` runs them | `03_governance.txt`, `12_access_test.txt` | built (persona switch); to do (non-admin principal) |
| ML + GenAI | A predictive, explainable next best product, valued in CLV | gold_*, silver_digital_events, clv_* | model `cross_sell_propensity`, gold_customer_clv, gold_cross_sell_recommendations, gold_recommendation_explanations | MLflow, UC model registry, serverless jobs, ai_query, MLflow GenAI evaluation | `EVAL_PROTOCOL.md`: out-of-time top-decile lift vs bar and baseline; rule checks and LLM judge on explanations | `04_ml.txt`, `05_genai.txt`, `10_eval_protocol.txt`, `11_genai_judge.txt` | built; to do (protocol test, judge) |
| Lakebase | Fast single-customer reads for bankers and a transactional record of every outcome, with branch security in Postgres | serving_* | pg_* synced tables, app.* views, app.banker_feedback, UC banker_feedback | Lakebase Autoscaling, synced tables, Postgres RLS, OAuth database credentials | Temporary role with the app's exact grants: roster banker sees own branches, others see 0, base tables denied, other-branch insert rejected | `06_lakebase.txt` | built |
| Genie | Analysts ask about adoption, CLV, recommendations and outcomes in plain language, instead of a new dashboard per question | 5 gold tables incl. banker_feedback | answers | Genie space, instructions, example SQL, benchmarks | Benchmark evaluation runs; a question on banker outcomes | `07_genie.txt`, `09_feedback_loop.txt` | built |
| App | The banker's screen: my book, the customer 360, the explained next best product, recording the outcome | app.* views | app.banker_feedback rows | Databricks Apps (Streamlit), Lakebase resource, forwarded user identity | Streamlit AppTest against live views; outcomes appear in UC and Genie | `08_app_test.txt`, `09_feedback_loop.txt` | built |

## 3. Tables

**Bronze** (raw as landed, plus `_source_file` and `_ingested_at`). Grain: one row per source record, duplicates included.

| Table | Grain |
|---|---|
| bronze_core_customers | one row per core banking customer record |
| bronze_deposit_accounts | one row per deposit account record |
| bronze_loan_customers / bronze_loans | one row per loan-system customer / loan record |
| bronze_card_customers / bronze_card_accounts / bronze_card_transactions | one row per card customer / card / transaction record |
| bronze_digital_users / bronze_digital_events | one row per digital user / event record |

**Silver** (cleaned and conformed)

| Table | Grain | What happens |
|---|---|---|
| silver_core_customers | one row per core customer | exact duplicates removed, typed |
| silver_customer_identities | one row per (system, source customer ID) | normalized names, email, phone, ZIP for matching |
| silver_deposit_accounts, silver_loans, silver_card_accounts, silver_digital_events | one row per account / loan / card / event that passed every rule | rules applied, failures routed to quarantine |
| silver_card_transactions | one row per transaction | typed |
| quarantine_records | one row per failed record | source table, failed rule names, original record as JSON |
| customer_identity_map | one row per (system, source customer ID) | customer_360_id and the rule that matched it |

**Gold** (business-ready; masks and row filter attached)

| Table | Grain |
|---|---|
| gold_customer_360 | one row per customer |
| gold_product_holdings | one row per product account |
| gold_customer_clv | one row per customer |
| gold_cross_sell_recommendations | one row per (customer, recommended product), up to 3 per customer |
| gold_recommendation_explanations | one row per customer with a #1 recommendation |

Supporting: gold_digital_product_interest (one row per customer and product viewed), banker_feedback (one row per recorded outcome), c360_access_entitlements, c360_banker_assignments, clv_product_assumptions, clv_parameters, serving_* (owner-only copies for sync).

**Cleanup (to do):** the synced-table pipelines currently store their event logs and staging tables in the same schema. Move them to a separate schema `c360_bank.sync_staging` so the business schema shows only business tables.

## 4. Bundle layout

`databricks.yml` variables: `catalog` (c360_bank), `schema` (customer_lifetime_value), `warehouse_id`, `app_postgres_role`. One target, `febar`. LLM endpoint: `databricks-claude-haiku-5-5` (to add as a variable).

| File | Resources |
|---|---|
| resources/schema.yml | schema, volumes `raw` and `ground_truth` |
| resources/data_job.yml | job c360_generate_raw_data (simulates the source systems landing files) |
| resources/pipeline.yml | pipeline c360_lakeflow_pipeline |
| resources/build_job.yml | job c360_build (policies, pipeline, tags); folded into c360_end_to_end (to do) |
| resources/ml_job.yml | experiment, job c360_ml; folded into c360_end_to_end (to do) |
| resources/serve_job.yml | jobs c360_serve and c360_feedback_sync; c360_serve folded into c360_end_to_end (to do) |
| resources/lakebase.yml | Lakebase project, 4 synced tables |
| resources/genie.yml | Genie space |
| resources/app.yml | app c360-banker with its Lakebase resource |

## 5. Orchestration (to do)

One Lakeflow Job, **c360_end_to_end**, triggered by **file arrival** on `/Volumes/c360_bank/customer_lifetime_value/raw/_landing/`. The generator writes its data files first and a marker file last, so the job starts only when a full end-of-day drop has landed. Data files get date-stamped names per drop, so Auto Loader picks up each new drop incrementally (it skips files overwritten under the same name).

Task order:

1. `access_policies`: entitlement table, persona and mask functions
2. `refresh_pipeline`: bronze to gold
3. `pii_tags`
4. `clv_assumptions`, then `train_and_score`, then `explanations`
5. `serving_tables`, then `refresh_synced_tables`, then `postgres_setup`
6. Checks in parallel: `eval_protocol` (out-of-time test), `genai_judge`, `access_test` (non-admin principal)

`c360_feedback_sync` stays a separate hourly job, because outcomes arrive during the day from the app.

## 6. Time plan (a fresh engineer, with this repo)

| Stage | Hours |
|---|---|
| Workspace, catalog, bundle skeleton, synthetic generator | 1.0 |
| Lakeflow pipeline and quality checks | 1.5 |
| Unity Catalog policies and access test | 0.75 |
| ML model, CLV, explanations, evaluation | 1.5 |
| Lakebase sync, Postgres security, feedback loop | 1.0 |
| Genie space and benchmarks | 0.5 |
| App | 1.0 |
| Orchestration job and evidence collection | 0.75 |
| **Total** | **8.0** |

Remaining work to finish this plan: out-of-time evaluation, LLM judge, non-admin access test, the end-to-end job with file arrival trigger, sync staging schema cleanup, and refreshing `evidence/00_setup.txt`. About 3 hours.
