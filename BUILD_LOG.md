# Build Log

| Date | What I tried | What failed | What I changed and why |
|---|---|---|---|
| 2026-11-18 | Wrote FEBAR_CONTEXT.md, CLAUDE.md pointer and .gitignore; cloned the GitHub repo | My FEVM account had no active workspaces, and the old banking demo workspace has likely expired | Prepared a new AWS Stable Serverless FEVM request |
| 2026-11-18 | Checked whether the FEVM workspace can create a catalog | The workspace is admin only on the workspace, not on the regional metastore, so `CREATE CATALOG` will probably fail | Chose catalog `c360_bank` and schema `customer_lifetime_value`, and recorded it in DECISIONS.md |
| 2026-11-18 | Submitted FEVM workspace `febar-c360-bank` (AWS Stable Serverless, us-west-2, 30 days). Resource ID 01a1ef6a-e164-72d6-9837-24fc5ac81c54 | (none so far; state Pending) | Expires 2026-12-18; request an extension before then if needed |
| 2026-11-18 | Checked FEVM status for febar-c360-bank | (none) | Workspace Active at https://fevm-febar-c360-bank.cloud.databricks.com; next: CLI profile `febar` |
| 2026-11-18 | Read-only checks with profile `febar`: auth describe, current-user, apps list, catalogs list | (none) | Workspace admin confirmed; Apps API works (0 apps); FEVM auto-created `febar_c360_bank_catalog`; `c360_bank` does not exist yet |
| 2026-11-18 | Submitted FEVM Standalone Catalog `c360_bank` (us-west-2, 90 days) via the FEVM web form, because the CLI-side submit cannot set the catalog name. Resource ID 01a1ef7b-783c-72e4-b354-a748ecfdbd10 | (none so far; state Pending) | Catalog expires 2027-02-16, after the workspace (2026-12-18) |
| 2026-11-18 | Catalog `c360_bank` had no schema (FEVM creates only the catalog). Added minimal bundle (databricks.yml + resources/schema.yml); validate + deploy created `c360_bank.customer_lifetime_value` | (none) | Second deploy: 0 created, 1 unchanged (idempotent). Evidence in evidence/00_setup.txt with user identities redacted |
