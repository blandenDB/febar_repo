# Customer 360 and next best product for a regional bank

A working Databricks prototype: four bank systems land as raw files, become one governed customer 360, drive an explainable next best product valued in customer lifetime value (CLV), and reach relationship bankers in an app whose outcomes flow back for analysts to question in plain language.

**All data is synthetic.** No real customers, people, or bank systems appear anywhere in this repository or the workspace.

## The story

[YOUR WORDS] A regional bank (1.3M customers, 522 branches) cannot see which products a customer holds without searching an account lookup portal and one Power BI dashboard per product line, and it has no way to know which product to offer next. Its cross-sell campaign response rate is 1.5%; the win at 6 months is 4% or more. This prototype shows the path: a complete customer 360, a next best product ranked by expected CLV uplift with a plain-English reason, and a banker app that records what happened. Full framing: [`USE_CASE.md`](USE_CASE.md).

Personas: **EVP Data & Analytics** (executive sponsor, owns the response rate and CLV), **Chief Data Officer** (domain owner, owns a trusted, governed customer view), **business analysts** (Genie), **relationship bankers** (the app).

## The journey, stage by stage

Each stage reads the previous stage's output. Every claim below links to the text evidence that proves it ran.

| # | Stage | What it does | Result | Evidence |
|---|---|---|---|---|
| 1 | **Raw data** | Synthetic end-of-day files from core banking, loans, cards and digital banking, each with its own customer ID and planted quality problems | 2,325,424 raw rows across 9 files; ground truth kept apart | [`01_raw_data.txt`](evidence/01_raw_data.txt) |
| 2 | **Lakeflow** | Auto Loader into bronze; dedupe, typing and 13 quality rules into silver, failures quarantined with the rule they broke; people matched across systems; gold customer 360 | Duplicates removed equal those planted (1,000 / 1,986 / 639); quarantine matches planted counts for every rule except `card_known_customer`, 479 of 480 (likely one random orphan ID that collides with a real customer ID); matching precision 1.0, recall 0.994 to 0.9997 against ground truth; reruns add no rows | [`02_pipeline.txt`](evidence/02_pipeline.txt) |
| 3 | **Unity Catalog** | Entitlement-driven column masks and branch row filters on every gold table; PII tags; comments | Analyst: 50,195 customers, names, email and date of birth masked. Banker (2 branches): only those branches, full detail. No entitlement: 0 rows. Proven with a **non-admin service principal**, which also cannot read silver PII or change its own access | [`03_governance.txt`](evidence/03_governance.txt), [`12_access_test.txt`](evidence/12_access_test.txt) |
| 4 | **ML** | Point-in-time propensity model over 8 products (MLflow, UC model registry); CLV from illustrative assumptions; next best product ranked by expected CLV uplift among products at least 3x their base rate | Out-of-time test under a protocol committed before the test: top-decile lift **8.2x**, **1.27x** a simple page-view baseline; both pre-set bars met | [`04_ml.txt`](evidence/04_ml.txt), [`10_eval_protocol.txt`](evidence/10_eval_protocol.txt), [`EVAL_PROTOCOL.md`](EVAL_PROTOCOL.md) |
| 5 | **GenAI** | `ai_query` with Claude Haiku 5.5 writes a "Why" and an "Opener" for each #1 recommendation from listed facts only; Claude Sonnet 5.5 judges a sample | Judge missed the bar twice, then passed (97% grounded, 95% all checks); the latest end-to-end run: 96% / 93%. Every run is kept | [`05_genai.txt`](evidence/05_genai.txt), [`11_genai_judge.txt`](evidence/11_genai_judge.txt) |
| 6 | **Lakebase** | Synced tables serve the 360 view and recommendations; the app writes banker outcomes to Postgres; row-level security by branch; outcomes copied back to UC | App role: own branches only, base tables denied, other-branch inserts rejected; outcomes reach UC without duplicates on rerun | [`06_lakebase.txt`](evidence/06_lakebase.txt) |
| 7 | **Genie** | Analyst space over 5 gold tables with instructions, example SQL and 10 benchmark questions | Benchmarks 8/10, 8/10, then **10/10** after two documented instruction changes | [`07_genie.txt`](evidence/07_genie.txt) |
| 8 | **Databricks App** | Streamlit app for relationship bankers: My book (branch pie, product chart, table), Customer 360 with the explained next best product, record the outcome | Regression test against the live views passes (including a fixed selector bug); 3 recorded outcomes flowed app, Lakebase, UC, Genie | [`08_app_test.txt`](evidence/08_app_test.txt), [`09_feedback_loop.txt`](evidence/09_feedback_loop.txt) |

What is deployed, the job's task order and its schedule: [`00_setup.txt`](evidence/00_setup.txt).

## How it fits together

```
raw files (4 systems) -> Lakeflow pipeline: bronze -> silver + quarantine -> identity match -> gold
   -> Unity Catalog masks, row filters, tags
   -> ML: CLV, propensity model, ranked recommendations -> GenAI explanations (+ judge)
   -> serving copies -> Lakebase synced tables -> app views (Postgres RLS) -> Databricks App
   -> banker outcomes (Lakebase) -> Unity Catalog -> Genie
```

The full data flow, every table and its grain: [`BUILD_PLAN.md`](BUILD_PLAN.md).

One Lakeflow Job, `c360_end_to_end`, runs the 12 build and check tasks daily at 06:00 US Central (after the end-of-day batch): access policies, pipeline, tags, CLV, training and scoring, explanations, serving tables, Lakebase sync, Postgres security, then the out-of-time evaluation, the LLM judge and the non-admin access test.

## Repository

| Path | What |
|---|---|
| `databricks.yml`, `resources/` | Declarative Automation Bundle: schemas, volumes, pipeline, jobs, experiment, Lakebase project and synced tables, Genie space, app |
| `src/data/` | Synthetic data generator (fixed seed, planted issues, ground truth) |
| `src/pipeline/` | Lakeflow Spark Declarative Pipeline in SQL |
| `src/governance/` | Entitlements, masks, row filter, tags |
| `src/ai/` | CLV assumptions, training and scoring, explanations, evaluation protocol, LLM judge |
| `src/serve/` | Serving tables, synced table refresh, Postgres views and RLS, feedback copy to UC |
| `src/genie/` | Genie space definition (instructions, sample questions, benchmarks) |
| `src/app/` | Streamlit banker app |
| `tools/` | SQL runner, checks, evidence collector, access test, app test |
| `evidence/` | Text evidence for every stage |
| `USE_CASE.md`, `BUILD_PLAN.md`, `EVAL_PROTOCOL.md`, `DECISIONS.md`, `BUILD_LOG.md` | Framing, plan, evaluation rules, decisions, build history |

## Run it yourself

Requirements: a Databricks workspace with Unity Catalog, serverless compute, Lakebase, Databricks Apps and Foundation Model APIs; a catalog you can create schemas in (this build uses `c360_bank`); the Databricks CLI with a profile for the workspace.

```bash
databricks bundle validate --profile <profile>
databricks bundle deploy   --profile <profile>
databricks bundle run generate_raw_data --profile <profile>   # land the synthetic end-of-day files
databricks bundle run c360_end_to_end  --profile <profile>   # build, govern, score, serve, evaluate
databricks bundle run c360_banker_app  --profile <profile>   # start the app
python3 tools/collect_evidence.py --profile <profile>        # rebuild evidence/*.txt from the latest runs
```

Edit `databricks.yml` first: the workspace host, `warehouse_id`, and the catalog and schema names. After the app exists, `c360_end_to_end` grants its service principal access to the Lakebase views. To try the app as a banker, add yourself to `c360_banker_assignments` (the build adds the deploying user for branches BR001 and BR002).

## Limits, stated plainly

- Synthetic data makes signals clean. The model's 8.2x lift will not carry over to real data; the bar real data must clear is about 2.7x (1.5% to 4%). HELOC has too few positives for any claim.
- CLV figures use illustrative margin and retention assumptions (`DECISIONS.md`); they are not forecasts.
- Personas come from an entitlement table because this workspace cannot create account-level groups.
- A file arrival trigger was tried first and never evaluated in this workspace; the job runs on a schedule instead.
- Lakebase syncs cannot read tables with row filters or masks, so owner-only serving copies are synced and access is enforced again in Postgres.

## How AI was used

[YOUR WORDS] Built with an AI pair engineer under the rules in [`FEBAR_CONTEXT.md`](FEBAR_CONTEXT.md): every product, design and value decision was offered as options and made by me ([`DECISIONS.md`](DECISIONS.md)); every attempt, failure and fix is recorded in [`BUILD_LOG.md`](BUILD_LOG.md).
