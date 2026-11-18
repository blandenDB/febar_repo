# FE Bar Context (read before every task)

## 1. Purpose

I am building my own FE Bar submission: a working prototype that solves the **inability to analyze a complete 360 degree view of the customer and the bank products they use**, for a regional bank in Banking.

- Executive sponsor: EVP Data & Analytics
- Domain owner: CDO
- Success metric: customer lifetime value (CLV)

## 2. Non-negotiable FE Bar rules

- **One connected journey** starting from RAW synthetic or public data: Lakeflow ingest → Unity Catalog governance → Lakebase operational serving → ML or GenAI → Genie agent → Databricks App. Each stage consumes the output of the previous one. No disconnected demos.
- **The evaluator reads TEXT only.** Every stage needs committed text evidence that it ran: notebook outputs, run logs, query results, model output. Screenshots and recordings do not count. Source code alone fails the Build domain.
- **The GitHub repo must be readable by the evaluator** (public, or private EMU connected through the submission form).
- **Synthetic or public data only.** Never real customer data, customer names, people's names, internal system names or logos, in code, data, docs, commit messages or the deck.
- **My own work.** Never use or imitate Solution Builder output and never copy another person's build.
- **A business deck (PDF, .txt or .md) and an AI role-play are also required**; we prepare those at the end.

## 3. How you work with me

- Work in small, verifiable steps. After each step report: what you changed, how you verified it, what is next.
- **STOP AND ASK** before any decision about: the use case and story, personas, architecture and trade-offs, which data issues to plant, quality rules, access rules, AI approach, numbers in the value case, slide content and the narrative. Give two or three options with pros and cons and a recommendation; I decide.
- Keep `BUILD_LOG.md`: date, what you tried, what failed, what you changed and why. (I use it to write how I used AI.)
- Record every decision I make in `DECISIONS.md` (decision, options considered, why). I will rewrite it in my own words.
- Mark every narrative, opinion and decision section you draft (README, DECISIONS.md, deck notes) with **[YOUR WORDS]** so I rewrite it myself. The use case, the decisions, the numbers and the words must be mine.
- Never print, log or commit tokens, passwords or connection strings. Never guess a Databricks CLI profile; ask me.

## 4. Engineering conventions

- **Workspace:** ask me for the workspace URL and CLI profile, then use `--profile <name>` on every CLI command.
- **Unity Catalog:** catalog `c360_bank`, schema `customer_lifetime_value`. Everything lives in `c360_bank.customer_lifetime_value`. Raw files go in a UC volume under that schema.
- **Deploy with a Declarative Automation Bundle:** `databricks.yml` with variables (catalog, schema, warehouse_id, model endpoints) and one target; `resources/*.yml` for pipelines, jobs and apps. Commands: `databricks bundle validate`, `databricks bundle deploy`, `databricks bundle run <resource>`.
- **Prefer serverless:** serverless Lakeflow pipelines, serverless jobs, a serverless SQL warehouse.
- **Pipelines in SQL** (Lakeflow Spark Declarative Pipelines) unless Python is clearly better.
- **Idempotent reruns:** no duplicate rows when a step runs twice.
- **Run summaries:** every notebook task ends with `dbutils.notebook.exit(json.dumps(summary))`, a short JSON of what it did (rows, IDs, pass counts). Python file tasks print the same summary. The evidence step reads these back, because `.py` notebooks carry no outputs in the repo.
- **Agent skills:** if Databricks agent skills are installed, load the matching skill before each product (pipelines, Unity Catalog, Lakebase, apps, Genie, MLflow, jobs, bundles) and follow it.

## 5. Repository layout

```
README.md  FEBAR_CONTEXT.md  USE_CASE.md  BUILD_PLAN.md  EVAL_PROTOCOL.md
DECISIONS.md  BUILD_LOG.md  databricks.yml
resources/        bundle resource YAML (pipelines, jobs, apps)
src/data/         synthetic data generation
src/pipeline/     Lakeflow declarative pipelines
src/governance/   UC grants, tags, masks, row filters
src/ai/           ML / GenAI
src/serve/        Lakebase operational serving
src/genie/        Genie space definition and instructions
src/app/          Databricks App
tools/            helper scripts (evidence collection, etc.)
evidence/         committed text evidence of every run
deck/             business deck
```

`.gitignore` covers `.databricks/`, `.env`, `*.pem`, local notes and any credentials.

## 6. Definition of done (every task)

Code committed, deployed, run successfully in the workspace, verified with a query or API call whose output you show me, and a line added to `BUILD_LOG.md`.
